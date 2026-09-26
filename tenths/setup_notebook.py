"""
Setup notebook — a per car/track record of every setup you ran and how the car
behaved on it, written for an AI race engineer (Claude, Kiro, ...) to read.

Tenths only CAPTURES. It never recommends a setup and never writes a .sto file:
iRacing's setup files are encrypted, and the change list the agent produces is
typed into the garage by the driver, where iRacing validates every value. The
agent's instructions live in ENGINEER.md at the notebook root.

Layout (under config.NOTEBOOK_DIR):
    ENGINEER.md                     how an agent should use the notebook
    <car>/<track>.json              the data (one entry per .ibt, keyed by filename)
    <car>/<track>.md                human/agent-readable view, regenerated from the json
    <car>/<track>.notes.md          the driver's own notes and the experiment log for
                                    that track; created once, never overwritten
    <car>/car_notes.md              lessons about the CAR that carry across tracks;
                                    created once, never overwritten
    <car>/limits.json               optional garage ranges; see `tenths notebook limits`

WHERE EACH VALUE COMES FROM
    Garage settings   CarSetup in the session YAML — a snapshot taken in the garage.
    In-car settings   The live dc* channels (brake bias, TC, ABS, throttle map).
                      The YAML snapshot is NOT what was driven: on 2026-09-25 at
                      Road Atlanta it said TC 1 / ABS 4 / bias 53.0% while the car
                      ran TC 4 / ABS 3 / bias 51.5% every lap. Always prefer live.
    Lap times         analyzer.lap_times — the single source. iRacing publishes a
                      lap's time ~1.7 s after the line, so reading LapLastLapTime at
                      a lap's end gives the previous lap's time (TECH_DEBT A5).
    Carcass temps and wear only update when the car enters the pits, so they are
    captured as a "pit-in snapshot" when present.

A/B/A TESTS
    A baseline / change / baseline sequence of comparable sessions is reported
    as effect = B - mean(A, A2) with drift = A2 - A, so a change is judged
    separately from track and driver drift. The two A runs also feed the noise
    floor, which pairs each session with the latest earlier one on the same
    setup (not just the previous session).

WARM-UP LAPS
    Balance and platform are measured only on clean laps from the point the tyre
    pressures settled (< SETTLED_PRESSURE_FRACTION change per lap on every tyre).
    Cold tyres understeer more; including warm-up laps would make a baseline look
    worse than the car is and skew any before/after comparison. Pace still uses
    every clean lap.

BALANCE METRIC
    Steer demand = steering-wheel degrees needed to drive a 100 m-radius arc,
    derived per sample as steer / (yaw_rate / speed). Higher means the car needs
    more lock for the same rotation (more understeer); lower means it rotates more
    freely. The absolute number depends on the car's steering ratio and wheelbase,
    so it is only meaningful compared across sessions of the SAME car, or across
    speed bands and phases within one session. Countersteer events (steering
    against the direction of rotation under load) are the oversteer signal.

UNITS
    The notebook is a display boundary (see tenths/units.py). Everything renders
    in the Tenths display setting (`config.is_metric()`), which should match the
    garage so numbers can be typed straight back in. The CarSetup YAML is always
    metric regardless of what the garage shows, so setup strings are converted in
    `display_setting`. The json stores the YAML strings and SI measurements.

GARAGE LIMITS
    <car>/limits.json is filled by hand from the garage (the ranges are nowhere in
    the .ibt, and .sto files are encrypted). Values are in the display units named
    by each entry's "unit". "linked": true marks settings whose legal range moves
    with other settings (ride height, camber, toe, bump rubber gap): iRacing flags
    an illegal value in red, so the range there is only a hint.
"""

import json
import math
import os
import re
from datetime import datetime

import numpy as np

from tenths import config
from tenths.applog import get_logger
from tenths.tyres import CORNERS, inner_middle_outer
from tenths.units import mph_to_mps, mps_to_mph

log = get_logger(__name__)

SCHEMA_VERSION = 1

# ── Channels ──────────────────────────────────────────────────────────────────

# Live in-car adjustment channel -> the CarSetup leaf it overrides.
IN_CAR_CHANNELS = {
    "dcBrakeBias": "BrakePressureBias",
    "dcTractionControl": "TcSetting",
    "dcABS": "AbsSetting",
    "dcThrottleShape": "ThrottleShapeSetting",
}

EXTRA_CHANNELS = (
    list(IN_CAR_CHANNELS)
    + [f"{c}rideHeight" for c in CORNERS]
    + [f"{c}shockDefl" for c in CORNERS]
    + [f"{c}temp{p}" for c in CORNERS for p in ("CL", "CM", "CR")]
    + [f"{c}wear{p}" for c in CORNERS for p in ("L", "M", "R")]
    + ["OnPitRoad"]
)

# ── Setup classification ──────────────────────────────────────────────────────
# Leaves that are readings from the last pit stop, not settings.
_READING_LEAVES = ("LastHotPressure", "LastTempsOMI", "LastTempsIMO", "TreadRemaining")
# Leaves with no effect on the car.
_IGNORED_LEAVES = ("UpdateCount", "DashDisplayPage", "NightLedStripColor")
# Leaves the garage computes from other settings. Shown, never recommended directly.
_COMPUTED_LEAVES = ("CornerWeight", "FWtdist", "CrossWeight",
                    "CenterFrontSplitterHeight")   # no garage arrows on the Mustang GT3
_COMPUTED_SECTIONS = ("AeroBalanceCalc",)

# ── Analysis thresholds ───────────────────────────────────────────────────────
# A lap within this fraction of the best counts as clean. Practice laps with an
# off or a missed shift are 5-10 s slower; 3% (~2.5 s at an 82 s lap) keeps
# ordinary variation and drops those.
CLEAN_LAP_FRACTION = 1.03

BALANCE_MIN_SPEED_MPS = 12.0
BALANCE_MIN_LAT_G = 0.3
BALANCE_MAX_RADIUS_M = 800.0     # straighter than this, curvature is noise
BALANCE_MIN_SAMPLES = 60         # one second at 60 Hz per band/phase cell
PHASE_BRAKE_PCT = 5.0
PHASE_EXIT_THROTTLE_PCT = 50.0
# Speed bands in m/s: slow < 30 (108 km/h) <= medium < 45 (162 km/h) <= fast.
SPEED_BANDS = (("slow", 0.0, 30.0), ("medium", 30.0, 45.0), ("fast", 45.0, 1e9))
PHASES = ("entry", "mid", "exit")
# Lateral-g bins for the equal-g balance table. A faster driver spends more time
# at high g, where any car needs more lock; comparing sessions within the same g
# bin separates the car from the driver. Found 2026-09-25: the same setup read
# "+12.5 deg understeer" in the phase table only because the driver was 1.6 s faster.
G_BINS = ((0.3, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 9.9))
NEAR_LIMIT_G = 1.5
# A countersteer run this long is reported individually with its lap position —
# the moments a driver remembers ("the rear stepped out at T5").
COUNTERSTEER_REPORT_S = 0.25

COUNTERSTEER_MIN_LAT_G = 0.5
COUNTERSTEER_MIN_STEER_RAD = 0.05
COUNTERSTEER_MIN_YAW_RAD_S = 0.1
COUNTERSTEER_MIN_SAMPLES = 6     # 0.1 s at 60 Hz

# Cells need this many samples in both sessions to count toward the noise floor.
REPEATABILITY_MIN_SAMPLES = 200
# A session needs this many measured laps to serve as a comparison base.
MIN_COMPARABLE_LAPS = 2
AT_SPEED_MPS = 55.0              # ride height "at speed" (aero platform)
PRESSURE_STABLE_FRACTION = 0.01  # < 1% change between the last two laps
# Clean laps getting faster by at least this much per lap (least-squares slope)
# means the driver was still learning; 2026-09-25 21:34 ran -0.24 s/lap.
DRIVER_LEARNING_S_PER_LAP = -0.15
# Balance and platform are measured only from the first lap whose pressures moved
# less than this — earlier laps are tyre warm-up.
SETTLED_PRESSURE_FRACTION = 0.015

STEER_DEG_PER_RATIO = 0.01 * 180.0 / math.pi   # rad*m -> wheel degrees at 100 m radius


# ═════════════════════════════════════════════════════════════════════════════
# Setup extraction
# ═════════════════════════════════════════════════════════════════════════════

def flatten_setup(car_setup, prefix=""):
    """Flatten the nested CarSetup YAML into {"Chassis.LeftFront.Camber": "-4.0 deg"}."""
    flat = {}
    for key, value in (car_setup or {}).items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_setup(value, path))
        else:
            flat[path] = "" if value is None else str(value)
    return flat


def classify_setup(flat):
    """Split a flattened setup into (settings, computed). Readings are dropped."""
    settings, computed = {}, {}
    for path, value in flat.items():
        leaf = path.rsplit(".", 1)[-1]
        if leaf in _READING_LEAVES or leaf in _IGNORED_LEAVES:
            continue
        if leaf in _COMPUTED_LEAVES or any(f"{s}." in path for s in _COMPUTED_SECTIONS):
            computed[path] = value
        else:
            settings[path] = value
    return settings, computed


def _setup_key_for(settings, leaf):
    """The full settings path whose last component is `leaf`, if any."""
    for path in settings:
        if path.rsplit(".", 1)[-1] == leaf:
            return path
    return None


def _leading_number(text):
    match = re.match(r"\s*([-+]?\d+(?:\.\d+)?)", str(text))
    return float(match.group(1)) if match else None


def in_car_settings(df, laps, settings):
    """What was actually driven for each in-car adjustment, from live channels.

    Returns {setup_path_or_channel: {"value", "garage_value", "varied", "per_lap"}}.
    `value` is the most common value over the given laps.
    """
    result = {}
    for channel, leaf in IN_CAR_CHANNELS.items():
        if channel not in df.columns:
            continue
        per_lap = {}
        for lap in laps:
            values = df.loc[df["Lap"] == lap, channel].round(3)
            if not values.empty:
                per_lap[int(lap)] = float(values.mode().iat[0])
        if not per_lap:
            continue
        counts = {}
        for v in per_lap.values():
            counts[v] = counts.get(v, 0) + 1
        value = max(counts, key=counts.get)
        key = _setup_key_for(settings, leaf) or channel
        result[key] = {
            "value": value,
            "garage_value": settings.get(key),
            "varied": len(counts) > 1,
            "per_lap": per_lap,
        }
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Laps
# ═════════════════════════════════════════════════════════════════════════════

def session_lap_times(df, laps):
    """{lap: seconds} for the given laps with a real time, from analyzer.lap_times."""
    from tenths.analyzer import lap_times
    times = lap_times(df)
    return {int(lap): times[lap] for lap in laps if times.get(lap, 0.0) > 0}


def clean_laps(times, fraction=CLEAN_LAP_FRACTION):
    """Laps within `fraction` of the best, in lap order."""
    if not times:
        return []
    best = min(times.values())
    return sorted(lap for lap, t in times.items() if t <= best * fraction)


def tires_settled_from(df, threshold=SETTLED_PRESSURE_FRACTION):
    """First lap whose mean pressure moved less than `threshold` from the previous
    lap on every tyre, or None if the tyres never settled (or no pressure data).

    Road Atlanta 2026-09-25: +3.7, +3.2, +2.1, +1.2, +0.9 % per lap on the
    hottest tyre, so settled from lap 5 at 1.5%.
    """
    cols = [f"{c}pressure" for c in CORNERS if f"{c}pressure" in df.columns]
    if not cols or "Lap" not in df.columns:
        return None
    per_lap = df[df["Lap"] > 0].groupby("Lap")[cols].mean()
    for lap in per_lap.index:
        if lap - 1 not in per_lap.index:
            continue                     # no previous lap to compare against
        change = ((per_lap.loc[lap] - per_lap.loc[lap - 1]).abs() / per_lap.loc[lap]).max()
        if change < threshold:
            return int(lap)
    return None


# ═════════════════════════════════════════════════════════════════════════════
# Metrics — each takes a DataFrame restricted to the laps it should measure.
# LatAccel is in g and Brake/Throttle in percent (analyzer.parse_ibt normalises).
# ═════════════════════════════════════════════════════════════════════════════

def _speed_band(speed):
    for name, low, high in SPEED_BANDS:
        if low <= speed < high:
            return name
    return SPEED_BANDS[-1][0]


def _phase(brake, throttle):
    if brake > PHASE_BRAKE_PCT:
        return "entry"
    if throttle > PHASE_EXIT_THROTTLE_PCT:
        return "exit"
    return "mid"


def balance_profile(d, n_laps, sample_rate=60):
    """Steer demand by speed band and phase and by band x lateral g, how hard the
    car was driven, and countersteer events (per lap, and the long ones by position)."""
    needed = {"Speed", "YawRate", "SteeringWheelAngle", "LatAccel", "Brake", "Throttle"}
    if not needed.issubset(d.columns) or d.empty:
        return None

    speed = d["Speed"].to_numpy(dtype=float)
    yaw = d["YawRate"].to_numpy(dtype=float)
    steer = d["SteeringWheelAngle"].to_numpy(dtype=float)
    lat = d["LatAccel"].to_numpy(dtype=float)
    brake = d["Brake"].to_numpy(dtype=float)
    throttle = d["Throttle"].to_numpy(dtype=float)

    with np.errstate(divide="ignore", invalid="ignore"):
        curvature = np.where(speed > 0.1, yaw / np.maximum(speed, 0.1), 0.0)
        ratio = steer / curvature

    usable = ((speed > BALANCE_MIN_SPEED_MPS)
              & (np.abs(lat) > BALANCE_MIN_LAT_G)
              & (np.abs(curvature) > 1.0 / BALANCE_MAX_RADIUS_M)
              & (np.sign(steer) == np.sign(curvature))
              & np.isfinite(ratio))

    cells, g_cells = {}, {}
    for i in np.flatnonzero(usable):
        band, phase = _speed_band(speed[i]), _phase(brake[i], throttle[i])
        cells.setdefault((band, phase), []).append(ratio[i])
        if phase != "entry":        # braking adds its own steer demand; compare off-brake
            g = abs(lat[i])
            for low, high in G_BINS:
                if low < g <= high:
                    g_cells.setdefault((band, _g_label(low, high)), []).append(ratio[i])
                    break

    steer_demand = {}
    for band, _, _ in SPEED_BANDS:
        row = {}
        for phase in PHASES:
            values = cells.get((band, phase), [])
            row[phase] = (round(float(np.median(values)) * STEER_DEG_PER_RATIO, 1)
                          if len(values) >= BALANCE_MIN_SAMPLES else None)
        steer_demand[band] = row

    overall = (round(float(np.median(ratio[usable])) * STEER_DEG_PER_RATIO, 1)
               if usable.sum() >= BALANCE_MIN_SAMPLES else None)

    by_g = {}
    for band, _, _ in SPEED_BANDS:
        by_g[band] = {}
        for low, high in G_BINS:
            values = g_cells.get((band, _g_label(low, high)), [])
            by_g[band][_g_label(low, high)] = {
                "deg": (round(float(np.median(values)) * STEER_DEG_PER_RATIO, 1)
                        if len(values) >= BALANCE_MIN_SAMPLES else None),
                "n": len(values),
            }
    cornering = usable & (brake <= PHASE_BRAKE_PCT)

    # Countersteer: steering against the rotation while the car is loaded.
    counter = ((np.abs(lat) > COUNTERSTEER_MIN_LAT_G)
               & (np.abs(steer) > COUNTERSTEER_MIN_STEER_RAD)
               & (np.abs(yaw) > COUNTERSTEER_MIN_YAW_RAD_S)
               & (np.sign(steer) != np.sign(yaw)))
    events = {phase: 0 for phase in PHASES}
    notable = []
    lap_col = d["Lap"].to_numpy() if "Lap" in d.columns else None
    pct_col = d["LapDistPct"].to_numpy(dtype=float) if "LapDistPct" in d.columns else None
    run_start = None
    for i, flag in enumerate(np.append(counter, False)):
        if flag and run_start is None:
            run_start = i
        elif not flag and run_start is not None:
            length = i - run_start
            if length >= COUNTERSTEER_MIN_SAMPLES:
                phase = _phase(brake[run_start], throttle[run_start])
                events[phase] += 1
                if length / sample_rate >= COUNTERSTEER_REPORT_S and lap_col is not None:
                    notable.append({
                        "lap": int(lap_col[run_start]),
                        "lap_pct": round(float(pct_col[run_start]), 1) if pct_col is not None else None,
                        "phase": phase,
                        "duration_s": round(length / sample_rate, 2),
                        "speed_mps": round(float(speed[run_start]), 1),
                    })
            run_start = None
    laps = max(n_laps, 1)

    return {
        "steer_demand_deg": steer_demand,
        "steer_demand_overall_deg": overall,
        "steer_demand_by_g": by_g,
        "near_limit_share": (round(float((np.abs(lat[cornering]) > NEAR_LIMIT_G).mean()), 2)
                             if cornering.any() else None),
        "lat_g_p99": round(float(np.quantile(np.abs(lat), 0.99)), 2),
        "countersteer_per_lap": {k: round(v / laps, 2) for k, v in events.items()},
        "countersteer_events": notable,
    }


def _g_label(low, high):
    return f">{low:g} g" if high >= 9 else f"{low:g}-{high:g} g"


def platform_profile(d):
    """Ride height and suspension travel (mm) over the given laps."""
    if d.empty or not any(f"{c}rideHeight" in d.columns for c in CORNERS):
        return None
    min_rh, defl = {}, {}
    for c in CORNERS:
        if f"{c}rideHeight" in d.columns:
            min_rh[c] = round(float(d[f"{c}rideHeight"].quantile(0.01)) * 1000.0, 1)
        if f"{c}shockDefl" in d.columns:
            defl[c] = round(float(d[f"{c}shockDefl"].quantile(0.99)) * 1000.0, 1)

    at_speed = {}
    fast = d[d["Speed"] > AT_SPEED_MPS] if "Speed" in d.columns else d.iloc[0:0]
    if len(fast) >= BALANCE_MIN_SAMPLES:
        for axle, pair in (("front", ("LF", "RF")), ("rear", ("LR", "RR"))):
            cols = [f"{c}rideHeight" for c in pair if f"{c}rideHeight" in fast.columns]
            if cols:
                at_speed[axle] = round(float(fast[cols].mean().mean()) * 1000.0, 1)
    rake = (round(at_speed["rear"] - at_speed["front"], 1)
            if {"front", "rear"} <= set(at_speed) else None)

    return {
        "min_ride_height_mm": min_rh,          # 1st percentile, so a kerb strike does not count
        "ride_height_at_speed_mm": at_speed,
        "rake_at_speed_mm": rake,
        "shock_deflection_p99_mm": defl,
    }


def _edges(corner, left, middle, right):
    """iRacing's left/middle/right channel values as {inner, middle, outer}.

    The orientation itself lives in tenths.tyres (left edge = outer on LF/LR).
    """
    inner, middle, outer = inner_middle_outer(corner, left, middle, right)
    return {"inner": inner, "middle": middle, "outer": outer}


def tire_profile(df, laps, times):
    """Surface temps, hot pressures and the pit-in snapshot.

    Surface temps and pressures come from the later half of the given laps, when
    the tyres are closest to their working state.
    """
    if not laps:
        return None
    late = laps[len(laps) // 2:]
    d = df[df["Lap"].isin(late)]

    surface = {}
    for c in CORNERS:
        cols = [f"{c}temp{p}" for p in ("L", "M", "R")]
        if all(col in d.columns for col in cols) and not d.empty:
            left, middle, right = (round(float(d[col].mean()), 1) for col in cols)
            surface[c] = _edges(c, left, middle, right)

    hot, stable = {}, None
    last_lap = laps[-1]
    for c in CORNERS:
        col = f"{c}pressure"
        if col in df.columns:
            hot[c] = round(float(df.loc[df["Lap"] == last_lap, col].mean()), 1)
    if len(laps) >= 2 and "LFpressure" in df.columns:
        changes = []
        for c in CORNERS:
            col = f"{c}pressure"
            if col in df.columns:
                a = df.loc[df["Lap"] == laps[-2], col].mean()
                b = df.loc[df["Lap"] == laps[-1], col].mean()
                if b:
                    changes.append(abs(b - a) / b)
        stable = bool(changes) and bool(max(changes) < PRESSURE_STABLE_FRACTION)

    return {
        "surface_c": surface,
        "hot_pressure_kpa": hot,
        "pressure_stable": stable,
        "pit_snapshot": pit_snapshot(df),
    }


def pit_snapshot(df):
    """Carcass temps and tread used at the last pit entry, or None.

    These channels hold their value between pit visits, so the reading is the last
    sample that differs from the file's starting value.
    """
    probe = "LFtempCM"
    if probe not in df.columns or df.empty:
        return None
    values = df[probe].to_numpy(dtype=float)
    changed = np.flatnonzero(np.abs(values - values[0]) > 0.05)
    if changed.size == 0:
        return None
    row = df.iloc[int(changed[-1])]

    carcass, used = {}, {}
    for c in CORNERS:
        cols = [f"{c}temp{p}" for p in ("CL", "CM", "CR")]
        if all(col in df.columns for col in cols):
            carcass[c] = _edges(c, *(round(float(row[col]), 1) for col in cols))
        wear_cols = [f"{c}wear{p}" for p in ("L", "M", "R")]
        if all(col in df.columns for col in wear_cols):
            left, middle, right = (round((1.0 - float(df[col].min())) * 100.0, 1)
                                   for col in wear_cols)
            used[c] = _edges(c, left, middle, right)
    return {"carcass_c": carcass, "tread_used_pct": used}


# ═════════════════════════════════════════════════════════════════════════════
# Session entry
# ═════════════════════════════════════════════════════════════════════════════

def _player(info):
    di = info.get("DriverInfo", {}) or {}
    idx = di.get("DriverCarIdx")
    for d in di.get("Drivers", []) or []:
        if d.get("CarIdx") == idx:
            return d
    return {}


def build_entry(filepath, info=None, df=None, track_map=None):
    """Build one notebook entry for an .ibt, or None if it cannot contribute.

    `info` (full session YAML) and `df` (parse_ibt with EXTRA_CHANNELS) may be
    passed in to avoid re-reading the file. `track_map` (track_map.load_track_map)
    names the corners where notable countersteer happened.
    """
    from tenths.analyzer import get_valid_laps, parse_ibt, read_session_yaml

    info = info if info is not None else read_session_yaml(filepath)
    car_setup = info.get("CarSetup")
    if not car_setup:
        log.info("Setup notebook: %s has no CarSetup section; skipped.",
                 os.path.basename(filepath))
        return None

    if df is None:
        df, _, _, _ = parse_ibt(filepath, extra_channels=EXTRA_CHANNELS)
    valid = get_valid_laps(df)
    times = session_lap_times(df, valid)
    clean = clean_laps(times)
    if not clean:
        log.info("Setup notebook: %s has no timed laps; skipped.", os.path.basename(filepath))
        return None

    settings, computed = classify_setup(flatten_setup(car_setup))
    clean_df = df[df["Lap"].isin(clean)]
    clean_times = [times[lap] for lap in clean]
    best_lap = min(times, key=times.get)

    # Car-behaviour metrics use only laps on settled tyres; warm-up laps
    # understeer more and would bias a before/after comparison.
    settled_from = tires_settled_from(df)
    measured = [lap for lap in clean if settled_from is not None and lap >= settled_from]
    if not measured:
        measured = clean
    measured_df = df[df["Lap"].isin(measured)]

    wi = info.get("WeekendInfo", {}) or {}
    di = info.get("DriverInfo", {}) or {}
    player = _player(info)
    sessions = (info.get("SessionInfo", {}) or {}).get("Sessions", []) or []

    flags = []
    if measured is clean and settled_from is None:
        flags.append("Tyres never settled (pressure still changing more than "
                     f"{SETTLED_PRESSURE_FRACTION:.1%} per lap) — balance uses all clean "
                     "laps, including warm-up.")
    if len(measured) < 3:
        flags.append(f"Balance measured on only {len(measured)} lap(s) — treat it as rough.")
    trend = pace_trend(clean, times)
    if trend is not None and trend <= DRIVER_LEARNING_S_PER_LAP:
        flags.append(f"Lap times fell {abs(trend):.2f} s/lap through the session — the driver "
                     "was still improving, so pace differences against other sessions are "
                     "partly the driver, not the setup.")
    tires = tire_profile(df, clean, times)
    if tires and tires["pressure_stable"] is False:
        flags.append("Tyre pressures were still rising on the last clean lap — "
                     "the tyres had not reached working temperature.")
    # Long countersteer moments from EVERY lap: a crash or big save happens on a
    # lap that is never clean, and it is the moment worth recording.
    moments = []
    all_laps = balance_profile(df[df["Lap"] > 0], 1)
    if all_laps:
        moments = _name_corners(all_laps, track_map)["countersteer_events"]
        for m in moments:
            m["clean_lap"] = m["lap"] in clean
    in_car = in_car_settings(df, clean, settings)
    if any(v["varied"] for v in in_car.values()):
        flags.append("In-car settings changed between clean laps; see per-lap values.")
    modified = str(di.get("DriverSetupIsModified", 0)) not in ("0", "False", "false")
    if modified:
        flags.append("Setup was modified in the garage and not saved under a new name.")

    return {
        "id": os.path.basename(filepath),
        "recorded": _recorded_from_filename(filepath),
        "session_types": sorted({str(s.get("SessionType", "")) for s in sessions} - {""}),
        "car": player.get("CarScreenName", ""),
        "car_path": player.get("CarPath", ""),
        "track": wi.get("TrackDisplayName", ""),
        "track_config": wi.get("TrackConfigName", "") or "",
        "track_id": wi.get("TrackID"),
        "conditions": {
            "air": wi.get("TrackAirTemp", ""),
            "track": wi.get("TrackSurfaceTemp", ""),
        },
        "setup_name": str(di.get("DriverSetupName", "") or ""),
        "setup_modified": modified,
        "settings": settings,
        "computed": computed,
        "in_car": in_car,
        "pace": {
            "valid_laps": len(valid),
            "clean_laps": clean,
            "lap_times_s": times,
            "best_s": round(times[best_lap], 3),
            "best_lap": best_lap,
            "clean_mean_s": round(float(np.mean(clean_times)), 3),
            "clean_std_s": round(float(np.std(clean_times)), 3) if len(clean_times) > 1 else 0.0,
            # Top speed picks the downforce trim (car manuals give speed bands).
            "top_speed_mps": round(float(clean_df["Speed"].max()), 2),
            "tires_settled_from_lap": settled_from,
            "measured_laps": measured,
            "measured_mean_s": round(float(np.mean([times[l] for l in measured])), 3),
            "clean_trend_s_per_lap": trend,
        },
        "balance": _name_corners(balance_profile(measured_df, len(measured)), track_map),
        "platform": platform_profile(measured_df),
        "tires": tires,
        "countersteer_moments": moments,
        "flags": flags,
    }


def pace_trend(laps, times):
    """Least-squares slope of clean lap time against lap number (s/lap), or None."""
    if len(laps) < 4:
        return None
    x = np.array(laps, dtype=float)
    y = np.array([times[lap] for lap in laps], dtype=float)
    return round(float(np.polyfit(x, y, 1)[0]), 3)


def _name_corners(balance, track_map):
    if not balance or not track_map:
        return balance
    from tenths.track_map import get_turn_name
    for event in balance.get("countersteer_events", []):
        if event.get("lap_pct") is not None:
            event["corner"] = get_turn_name(track_map, event["lap_pct"])
    return balance


def _recorded_from_filename(filepath):
    match = re.search(r"(\d{4}-\d{2}-\d{2}) (\d{2})-(\d{2})-(\d{2})\.ibt$",
                      os.path.basename(filepath))
    if match:
        return f"{match.group(1)} {match.group(2)}:{match.group(3)}"
    return datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%Y-%m-%d %H:%M")


# ═════════════════════════════════════════════════════════════════════════════
# Storage
# ═════════════════════════════════════════════════════════════════════════════

def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "unknown"


def notebook_paths(car_slug, track_slug, root=None):
    """(json, md, notes) paths for one car/track notebook."""
    folder = os.path.join(root or config.NOTEBOOK_DIR, _slug(car_slug))
    base = os.path.join(folder, _slug(track_slug))
    return base + ".json", base + ".md", base + ".notes.md"


def load_notebook(json_path):
    if not os.path.exists(json_path):
        return {"schema": SCHEMA_VERSION, "entries": []}
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def add_entry(notebook, entry):
    """Insert or replace `entry` (keyed by id) and keep entries in time order."""
    entries = [e for e in notebook.get("entries", []) if e.get("id") != entry["id"]]
    entries.append(entry)
    entries.sort(key=lambda e: (e.get("recorded", ""), e.get("id", "")))
    notebook["entries"] = entries
    notebook["schema"] = SCHEMA_VERSION
    return notebook


def record_session(filepath, file_info=None, root=None):
    """Add one .ibt to its notebook and regenerate the markdown view.

    Returns the markdown path, or None when the session had nothing to record.
    Raises on I/O errors; pipeline callers treat that as non-fatal.
    """
    from tenths.jsonio import to_jsonable
    from tenths.process import parse_filename

    file_info = file_info or parse_filename(filepath)
    if not file_info:
        return None
    track_map = None
    try:
        from tenths.track_map import load_track_map
        track_map = load_track_map(file_info["track"])
    except Exception as exc:             # corner names are cosmetic
        log.info("Setup notebook: no track map for %s: %s", file_info["track"], exc)
    entry = build_entry(filepath, track_map=track_map)
    if entry is None:
        return None
    summary_path, summary = find_session_summary(filepath, file_info)
    if summary:
        entry["report"] = os.path.join(os.path.dirname(summary_path), "session_report.html")
        entry["corners"] = corners_from_summary(summary)

    json_path, md_path, notes_path = notebook_paths(
        file_info["car"], file_info["track"], root)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)

    notebook = add_entry(load_notebook(json_path), entry)
    notebook["car"] = entry["car"] or file_info["car"]
    notebook["track"] = " — ".join(x for x in (entry["track"], entry["track_config"]) if x)

    _write_text(json_path, json.dumps(to_jsonable(notebook), indent=1))
    limits = load_limits(file_info["car"], root)
    _write_text(md_path, render_markdown(notebook, limits))
    if not os.path.exists(notes_path):
        _write_text(notes_path, _NOTES_TEMPLATE.format(car=notebook["car"],
                                                       track=notebook["track"]))
    car_notes = car_notes_path(file_info["car"], root)
    if not os.path.exists(car_notes):
        _write_text(car_notes, _CAR_NOTES_TEMPLATE.format(car=notebook["car"]))
    ensure_engineer_guide(root)
    return md_path


def find_session_summary(filepath, file_info, telemetry_root=None):
    """(path, data) of the session_summary.json generated from this .ibt, or (None, None).

    Session folders are <root>/<car>/<track>/<date>/<time>[-N]; the summary's
    source_file identifies which one came from this file.
    """
    import glob
    root = telemetry_root or config.TELEMETRY_ROOT
    base = os.path.join(root, file_info["car"], file_info["track"], file_info["date"])
    name = os.path.basename(filepath)
    for folder in sorted(glob.glob(os.path.join(glob.escape(base), file_info["time"] + "*"))):
        path = os.path.join(folder, "session_summary.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if data.get("source_file") == name:
            return path, data
    return None, None


def corners_from_summary(summary):
    """Per-corner figures from the session report, in SI.

    Only multi-lap figures are taken (average apex speed, its spread, time lost
    against the session's best sector) — the report's single-lap "best lap"
    figures depend on analyzer lap timing that is known to be off by one lap.
    The report only covers corners with a heavy-braking zone (TECH_DEBT A1).
    """
    variance = {c.get("turn_name"): c for c in summary.get("corner_variance", []) or []}
    trail = {c.get("turn_name"): c for c in summary.get("trail_braking", []) or []}

    def mps(value):
        return round(mph_to_mps(value), 2) if isinstance(value, (int, float)) else None

    corners = []
    for zone in summary.get("braking_zones", []) or []:
        name = zone.get("turn_name")
        cv, tb = variance.pop(name, {}), trail.get(name, {})
        corners.append({
            "turn": name,
            "pct": zone.get("position_pct"),
            "entry_speed_mps": mps(zone.get("entry_speed_mph")),
            "apex_avg_mps": mps(zone.get("apex_avg_mph")),
            "min_speed_spread_mps": mps(zone.get("min_speed_spread_mph")),
            "time_loss_s": cv.get("time_loss_s"),
            "trail_diagnosis": tb.get("diagnosis"),
        })
    for name, cv in variance.items():         # time-loss corners without a braking zone
        corners.append({"turn": name, "pct": cv.get("position_pct"),
                        "time_loss_s": cv.get("time_loss_s")})
    return sorted(corners, key=lambda c: c.get("pct") or 0)


def _write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def car_notes_path(car_slug, root=None):
    return os.path.join(root or config.NOTEBOOK_DIR, _slug(car_slug), "car_notes.md")


def limits_path(car_slug, root=None):
    return os.path.join(root or config.NOTEBOOK_DIR, _slug(car_slug), "limits.json")


def load_limits(car_slug, root=None):
    path = limits_path(car_slug, root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable limits file %s: %s", path, exc)
        return None


def write_limits_template(car_slug, root=None):
    """Create limits.json listing every setting seen for this car, values unset.

    Never overwrites an existing file. Returns (path, created).
    """
    path = limits_path(car_slug, root)
    if os.path.exists(path):
        return path, False
    folder = os.path.dirname(path)
    seen = {}
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith(".json") and name != "limits.json":
                for e in load_notebook(os.path.join(folder, name)).get("entries", []):
                    for key, value in e.get("settings", {}).items():
                        seen.setdefault(key, value)
    template = {
        "_about": ("Garage limits for this car. Fill min/max/step from the iRacing "
                   "garage (numbers only, in 'unit'). Leave null if unknown. "
                   "'options' is for non-numeric settings; 'linked': true when the "
                   "legal range depends on other settings."),
        "settings": {key: {"example": display_setting(value), "min": None, "max": None,
                           "step": None, "unit": None, "linked": False}
                     for key, value in seen.items()},
    }
    os.makedirs(folder, exist_ok=True)
    _write_text(path, json.dumps(template, indent=1))
    return path, True


# ═════════════════════════════════════════════════════════════════════════════
# Markdown rendering (display boundary)
# ═════════════════════════════════════════════════════════════════════════════

def _fmt_time(seconds):
    if seconds is None:
        return "—"
    return f"{int(seconds // 60)}:{seconds % 60:06.3f}"


# The CarSetup YAML in an .ibt is always metric (kPa, mm, N/mm, L, Nm), whatever
# units the garage displays — confirmed 2026-09-25: every Mustang file says
# "159 kPa" while the garage shows "23.0 psi". Imperial display converts here.
_IMPERIAL_SETTING_UNITS = {   # metric unit -> (factor, imperial unit, decimals)
    "kPa": (0.145038, "psi", 1),
    "mm": (1 / 25.4, "in", 3),
    "N/mm": (5.71015, "lbs/in", 0),
    "N": (0.224809, "lbs", 0),
    "L": (0.264172, "gal", 1),
    "Nm": (0.737562, "ft-lbs", 0),
}
_SETTING_VALUE = re.compile(r"\s*([-+]?)(\d+(?:\.\d+)?)\s*(kPa|N/mm|mm|Nm|N|L)\s*")


def display_setting(value, metric=None):
    """A metric setup string in the user's display units ("159 kPa" -> "23.1 psi").

    Values without a convertible unit (degrees, clicks, %, names) pass through.
    """
    metric = config.is_metric() if metric is None else metric
    if value is None or metric:
        return value
    match = _SETTING_VALUE.fullmatch(str(value))
    if not match:
        return value
    sign, number, unit = match.groups()
    factor, new_unit, decimals = _IMPERIAL_SETTING_UNITS[unit]
    converted = float(number) * factor
    text = f"{converted:.{decimals}f}"
    return f"{'-' if sign == '-' else sign}{text} {new_unit}"


def _display_units():
    if config.is_metric():
        return {"pressure": "kPa", "temp": "C", "length": "mm"}
    return {"pressure": "psi", "temp": "F", "length": "in"}


def _p(kpa, units):
    if kpa is None:
        return "—"
    return f"{kpa * 0.145038:.1f}" if units["pressure"] == "psi" else f"{kpa:.1f}"


def _t(celsius, units):
    if celsius is None:
        return "—"
    return f"{celsius * 9 / 5 + 32:.0f}" if units["temp"] == "F" else f"{celsius:.0f}"


def _l(mm, units):
    if mm is None:
        return "—"
    return f"{mm / 25.4:.3f}" if units["length"] == "in" else f"{mm:.1f}"


def _snap_to_step(text, spec):
    """Round a converted value to the garage's step ("23.1 psi" -> "23.0 psi").

    A metric YAML value converted to imperial lands between garage steps; show
    the value the garage itself displays.
    """
    if not spec or not spec.get("step") or not text:
        return text
    match = re.fullmatch(r"([-+]?)(\d+(?:\.\d+)?) (.+)", str(text))
    if not match or match.group(3) != spec.get("unit"):
        return text
    sign, number, unit = match.groups()
    step = float(spec["step"])
    snapped = round(float(number) / step) * step
    # Keep the precision the value was shown with, or the step's if finer.
    step_decimals = len(str(spec["step"]).partition(".")[2])
    decimals = max(step_decimals, len(number.partition(".")[2]))
    return f"{sign}{snapped:.{decimals}f} {unit}"


def _conditions_temp(text, units):
    """'26.06 C' from the session header, in display units."""
    value = _leading_number(text)
    return f"{_t(value, units)} °{units['temp']}" if value is not None else (text or "—")


def _limit_text(spec):
    """One-cell summary of a limits.json entry."""
    if not spec:
        return ""
    if spec.get("options"):
        text = " / ".join(spec["options"])
    elif spec.get("min") is not None and spec.get("max") is not None:
        text = f"{spec['min']:g}–{spec['max']:g} {spec.get('unit', '')}".rstrip()
        if spec.get("step") is not None:
            text += f", step {spec['step']:g}"
    else:
        text = ""
    if spec.get("linked"):
        text = (text + "; " if text else "") + "linked — iRacing checks legality"
    return text


def _speed(mps):
    if config.is_metric():
        return f"{mps * 3.6:.0f} km/h"
    return f"{mps_to_mph(mps):.0f} mph"


def _band_label(name, low, high):
    metric = config.is_metric()

    def conv(mps):
        return mps * 3.6 if metric else mps_to_mph(mps)
    unit = "km/h" if metric else "mph"
    if low <= 0:
        return f"{name} (< {conv(high):.0f} {unit})"
    if high >= 1e8:
        return f"{name} (> {conv(low):.0f} {unit})"
    return f"{name} ({conv(low):.0f}–{conv(high):.0f} {unit})"


def effective_settings(entry):
    """Garage settings with in-car values replaced by what was actually driven."""
    settings = dict(entry.get("settings", {}))
    for key, live in entry.get("in_car", {}).items():
        settings[key] = f"{live['value']:g} (driven)"
    return settings


def setup_diff(previous, current):
    """[(setting, old, new)] for settings that differ, using driven in-car values."""
    if previous is None:
        return []
    before, after = effective_settings(previous), effective_settings(current)
    changes = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if _normalise(old) != _normalise(new):
            changes.append((key, old, new))
    return changes


def _normalise(value):
    if value is None:
        return None
    return str(value).replace(" (driven)", "").strip()


def render_markdown(notebook, limits=None):
    entries = notebook.get("entries", [])
    car = notebook.get("car", "")
    track = notebook.get("track", "")
    latest = entries[-1] if entries else None
    units = _display_units()

    out = [
        f"# Setup notebook — {car} at {track}",
        "",
        "_Generated by Tenths from your telemetry after every session. Do not edit "
        "this file; it is rewritten each time. Your own observations go in the "
        "`.notes.md` file beside it. An agent should read `../../ENGINEER.md` first._",
        "",
        f"Units: pressure {units['pressure']}, temperature °{units['temp']}, "
        f"length {units['length']} (your Tenths display setting; match your garage "
        f"with `tenths config --units`).",
        f"Garage limits file: {'present' if limits else 'not yet created (`tenths notebook limits <car>`)'}.",
        "",
        "## Sessions",
        "",
        "Sessions with fewer than "
        f"{MIN_COMPARABLE_LAPS} measured laps (e.g. a stint cut short by a crash) are "
        "listed but never used as a comparison base.",
        "",
        "| # | Recorded | Setup | Best | Clean avg (laps) | Lap spread | Air / track | Compared with | Changes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(entries, 1):
        pace = e["pace"]
        base = comparison_base(entries, i - 1)
        prev = entries[base] if base is not None else None
        n_changes = len(setup_diff(prev, e)) if prev else None
        out.append(
            f"| {i} | {e['recorded']} | {e['setup_name'] or '—'} | {_fmt_time(pace['best_s'])} "
            f"| {_fmt_time(pace['clean_mean_s'])} ({len(pace['clean_laps'])}) "
            f"| ±{pace['clean_std_s']:.2f}s | {_conditions_temp(e['conditions'].get('air'), units)} / "
            f"{_conditions_temp(e['conditions'].get('track'), units)} "
            f"| {'—' if base is None else f'#{base + 1}'} "
            f"| {'—' if n_changes is None else n_changes} |")
    out.append("")

    if latest:
        out += ["## Latest setup (as driven)", ""]
        out += _setup_table(effective_settings(latest), latest.get("computed", {}), limits)

    out += _repeatability_section(entries)
    out += _aba_section(entries)
    out += ["## Session details (newest first)", ""]
    for i in range(len(entries) - 1, -1, -1):
        out += _session_section(entries, i, units)
    return "\n".join(out).rstrip() + "\n"


def _setup_table(settings, computed, limits=None):
    specs = (limits or {}).get("settings", {})
    out = ["| Section | Setting | Value | Garage range |", "|---|---|---|---|"]
    for key in settings:
        section, _, name = key.rpartition(".")
        value = _snap_to_step(display_setting(settings[key]), specs.get(key))
        out.append(f"| {section} | {name} | {value} | {_limit_text(specs.get(key))} |")
    for key in computed:
        section, _, name = key.rpartition(".")
        out.append(f"| {section} | {name} _(computed)_ | {display_setting(computed[key])} | |")
    return out + [""]


def _comparable(entry):
    laps = entry.get("pace", {}).get("measured_laps") or entry.get("pace", {}).get("clean_laps") or []
    return len(laps) >= MIN_COMPARABLE_LAPS


def comparison_base(entries, i):
    """Index of the session entry i is compared with: the most recent earlier
    session with enough measured laps to be a fair reference, or None."""
    for j in range(i - 1, -1, -1):
        if _comparable(entries[j]):
            return j
    return None


def _pace_detail(pace):
    parts = []
    if pace.get("measured_mean_s"):
        parts.append(f"average on measured (settled) laps {_fmt_time(pace['measured_mean_s'])}")
    if pace.get("clean_trend_s_per_lap") is not None:
        parts.append(f"clean-lap trend {pace['clean_trend_s_per_lap']:+.2f} s/lap "
                     "(negative = still getting faster)")
    return ("Pace detail: " + "; ".join(parts) + ".") if parts else ""


def _g_cells(bal):
    return (bal or {}).get("steer_demand_by_g") or {}


def _equal_g_section(bal, prev_bal):
    """Steer demand at equal lateral g — the table to compare sessions with."""
    by_g, prev = _g_cells(bal), _g_cells(prev_bal)
    if not by_g:
        return []
    labels = [_g_label(low, high) for low, high in G_BINS]
    out = [
        "**Balance at equal lateral g** (off-brake steer demand, degrees; brackets: change "
        "vs previous session). Use this table to compare sessions — a faster driver "
        "spends more time at high g, which needs more lock on any car.",
        "",
        "| Speed band | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]
    for name, low, high in SPEED_BANDS:
        cells = []
        for label in labels:
            cur = by_g.get(name, {}).get(label, {})
            old = prev.get(name, {}).get(label, {})
            v, pv = cur.get("deg"), old.get("deg")
            if v is None:
                cells.append(f"— (n={cur.get('n', 0)})" if cur.get("n") else "—")
            elif pv is None:
                cells.append(f"{v:.1f}")
            else:
                cells.append(f"{v:.1f} ({v - pv:+.1f})")
        out.append(f"| {_band_label(name, low, high)} | " + " | ".join(cells) + " |")
    share, p99 = bal.get("near_limit_share"), bal.get("lat_g_p99")
    if share is not None:
        prev_share = (prev_bal or {}).get("near_limit_share")
        was = f" (previous {prev_share:.0%})" if prev_share is not None else ""
        out += ["", f"Driving intensity: {share:.0%} of off-brake cornering above "
                    f"{NEAR_LIMIT_G:g} g{was}; 99th-percentile lateral {p99:.2f} g."]
    return out + [""]


def _corner_section(e, prev):
    corners = e.get("corners")
    if not corners:
        return []
    before = {c["turn"]: c for c in (prev or {}).get("corners") or []}

    def spd(value):
        return _speed(value) if value is not None else "—"

    out = ["**Corners** (from the session report — heavy-braking corners only; brackets: "
           "change vs previous session)", ""]
    if e.get("report"):
        # Notebooks live in NOTEBOOK_DIR/<car>/, so link relative to that depth.
        car_dir = os.path.join(config.NOTEBOOK_DIR, _slug(e.get("car_path") or "car"))
        rel = os.path.relpath(e["report"], car_dir).replace(os.sep, "/")
        out[0] += f" — [full report](<{rel}>)"
    out += ["", "| Corner | Lap % | Entry | Apex avg | Min-speed spread | Time lost | Trail braking |",
            "|---|---|---|---|---|---|---|"]
    for c in corners:
        apex = spd(c.get("apex_avg_mps"))
        old = before.get(c["turn"], {}).get("apex_avg_mps")
        if c.get("apex_avg_mps") is not None and old is not None:
            delta = c["apex_avg_mps"] - old
            apex += f" ({'+' if delta >= 0 else '-'}{_speed(abs(delta))})"
        loss = f"{c['time_loss_s']:.2f} s" if c.get("time_loss_s") is not None else "—"
        pct = f"{c['pct']:.1f}" if c.get("pct") is not None else "—"
        out.append(f"| {c['turn']} | {pct} | {spd(c.get('entry_speed_mps'))} | {apex} | "
                   f"{spd(c.get('min_speed_spread_mps'))} | {loss} | {c.get('trail_diagnosis') or '—'} |")
    return out + [""]


def _countersteer_events(events):
    if not events:
        return []
    out = [f"**Countersteer moments** of {COUNTERSTEER_REPORT_S:g} s or longer, all laps "
           "(corner names from community landmark data; check against iRacing's map):", ""]
    for e in events:
        corner = e.get("corner") or ""
        if not corner or corner.startswith("("):     # get_turn_name's "(12.3%)" fallback
            corner = "between named corners"
        where = corner
        pct = f" ({e['lap_pct']:.1f}% of lap)" if e.get("lap_pct") is not None else ""
        lap_kind = "" if e.get("clean_lap", True) else " — not a clean lap"
        out.append(f"- Lap {e['lap']}, {where}{pct}, {e['phase']}, {e['duration_s']:.2f} s "
                   f"at {_speed(e['speed_mps'])}{lap_kind}")
    return out + [""]


def _repeatability_section(entries):
    """How much the equal-g numbers moved between sessions with NO setup change.

    That spread is the noise floor: a setup change must move the numbers by more
    than this before it counts as an effect.
    """
    rows = []
    for i in range(1, len(entries)):
        base = same_setup_base(entries, i)
        if base is None:
            continue
        a, b = entries[base], entries[i]
        ga, gb = _g_cells(a.get("balance")), _g_cells(b.get("balance"))
        deltas = []
        for band in gb:
            for label, cell in gb[band].items():
                old = ga.get(band, {}).get(label, {})
                if (cell.get("deg") is not None and old.get("deg") is not None
                        and min(cell.get("n", 0), old.get("n", 0)) >= REPEATABILITY_MIN_SAMPLES):
                    deltas.append(abs(cell["deg"] - old["deg"]))
        if deltas:
            rows.append(f"| {base + 1} → {i + 1} | {len(deltas)} | {np.median(deltas):.1f} | "
                        f"{max(deltas):.1f} |")
    if not rows:
        return []
    return [
        "## Noise floor (same setup, different sessions)",
        "",
        "How far the equal-g steer demand moved between sessions with **no setup change** "
        f"(cells with at least {REPEATABILITY_MIN_SAMPLES} samples in both). A setup change "
        "has to beat this before it counts as an effect.",
        "",
        "| Sessions | Cells compared | Median change (deg) | Largest change (deg) |",
        "|---|---|---|---|",
        *rows,
        "",
    ]


def same_setup_base(entries, i):
    """The latest earlier comparable session run on exactly the same setup as
    session i, or None. Not necessarily the previous session: in an A/B/A test
    the two A runs are separated by B."""
    if not _comparable(entries[i]):
        return None
    for j in range(i - 1, -1, -1):
        if _comparable(entries[j]) and not setup_diff(entries[j], entries[i]):
            return j
    return None


def aba_tests(entries):
    """A/B/A tests: three consecutive comparable sessions where the first and last
    ran the same setup and the middle one changed it.

    Returns [(a, b, c)] indices. The second baseline measures how far conditions
    and the driver drifted during the test, so the change's effect can be
    separated from that drift:  effect = B - (A + A2) / 2,  drift = A2 - A.
    """
    comparable = [i for i, e in enumerate(entries) if _comparable(e)]
    tests = []
    for a, b, c in zip(comparable, comparable[1:], comparable[2:]):
        if setup_diff(entries[a], entries[b]) and not setup_diff(entries[a], entries[c]):
            tests.append((a, b, c))
    return tests


def _aba_effect(va, vb, vc):
    """(effect, drift) for one measurement, or None if any value is missing."""
    if va is None or vb is None or vc is None:
        return None
    return vb - (va + vc) / 2.0, vc - va


def _countersteer_total(entry):
    cs = (entry.get("balance") or {}).get("countersteer_per_lap") or {}
    return sum(cs.values()) if cs else None


def _aba_section(entries):
    tests = aba_tests(entries)
    if not tests:
        return []
    out = [
        "## A/B/A tests (drift-corrected)",
        "",
        "Baseline, change, baseline again. The repeat baseline shows how far track "
        "conditions and the driver moved during the test; the effect of the change is "
        "B minus the average of the two baselines. An effect smaller than the drift, or "
        "than the noise floor, is not evidence. Steer demand: higher = more understeer.",
        "",
    ]
    for a, b, c in tests:
        A, B, C = entries[a], entries[b], entries[c]
        changes = ", ".join(f"{key.rsplit('.', 1)[-1]} {display_setting(old)} → "
                            f"{display_setting(new)}" for key, old, new in setup_diff(A, B))
        out += [f"### Sessions {a + 1} / {b + 1} / {c + 1}: {changes}", ""]

        pace = _aba_effect(*(e["pace"].get("measured_mean_s") or e["pace"].get("clean_mean_s")
                             for e in (A, B, C)))
        if pace:
            out.append(f"- Lap time (settled-lap average): effect {pace[0]:+.3f} s, "
                       f"drift {pace[1]:+.3f} s (negative = faster).")
        cs = _aba_effect(*(_countersteer_total(e) for e in (A, B, C)))
        if cs:
            out.append(f"- Countersteer events per lap: effect {cs[0]:+.2f}, drift {cs[1]:+.2f}.")
        temps = [e["conditions"].get("track", "") for e in (A, B, C)]
        out += [f"- Track temperature: {' / '.join(str(t) for t in temps)}.", ""]

        labels = [_g_label(low, high) for low, high in G_BINS]
        rows, beaten, compared = [], 0, 0
        for name, low, high in SPEED_BANDS:
            cells = []
            for label in labels:
                vals = [_g_cells(e.get("balance")).get(name, {}).get(label, {}).get("deg")
                        for e in (A, B, C)]
                result = _aba_effect(*vals)
                if result is None:
                    cells.append("—")
                    continue
                effect, drift = result
                compared += 1
                if abs(effect) > abs(drift):
                    beaten += 1
                cells.append(f"{effect:+.1f} ({drift:+.1f})")
            rows.append(f"| {_band_label(name, low, high)} | " + " | ".join(cells) + " |")
        out += [
            "Steer demand at equal g — effect (drift), degrees:",
            "",
            "| Speed band | " + " | ".join(labels) + " |",
            "|---|" + "---|" * len(labels),
            *rows,
            "",
        ]
        if compared:
            out += [f"The effect is larger than the drift in {beaten} of {compared} cells.", ""]
    return out


def _measured_note(pace):
    laps = pace.get("measured_laps")
    if not laps:        # entries recorded before warm-up filtering
        return "Measured on all clean laps (recorded before warm-up filtering)."
    settled = pace.get("tires_settled_from_lap")
    listed = ", ".join(f"L{lap}" for lap in laps)
    if settled is None:
        return f"Measured on {listed} — tyres never settled, so warm-up laps are included."
    return (f"Measured on {listed} — tyres settled from lap {settled}; "
            f"earlier laps are warm-up and excluded.")


def _session_section(entries, i, units):
    e = entries[i]
    base = comparison_base(entries, i)
    prev = entries[base] if base is not None else None
    pace = e["pace"]
    out = [
        f"### {i + 1}. {e['recorded']} — {e['setup_name'] or 'unnamed setup'} "
        f"({', '.join(e['session_types']) or 'session'})",
        "",
        f"Source: `{e['id']}`",
        "",
    ]
    for flag in e.get("flags", []):
        out.append(f"> ⚠ {flag}")
    if e.get("flags"):
        out.append("")

    out.append(f"**Changes vs session {base + 1}** (the comparison base)" if prev is not None
               else "**Changes vs previous session**")
    out.append("")
    if prev is None:
        out.append("First session in this notebook." if i == 0 else
                   "No earlier session with enough measured laps to compare with.")
    else:
        diff = setup_diff(prev, e)
        if not diff:
            out.append("No setup changes.")
        else:
            out += ["| Setting | Before | After |", "|---|---|---|"]
            for key, old, new in diff:
                old, new = display_setting(old), display_setting(new)
                out.append(f"| {key} | {old if old is not None else '—'} | {new if new is not None else '—'} |")
    out.append("")

    if e.get("in_car"):
        out.append("**In-car settings driven** (live telemetry; garage snapshot in brackets)")
        out.append("")
        for key, live in e["in_car"].items():
            name = key.rsplit(".", 1)[-1]
            per_lap = ", ".join(f"L{lap}: {v:g}" for lap, v in live["per_lap"].items())
            note = f" — varied: {per_lap}" if live["varied"] else ""
            out.append(f"- {name}: **{live['value']:g}** [{live['garage_value'] or '—'}]{note}")
        out.append("")

    times = ", ".join(f"L{lap} {_fmt_time(t)}{'*' if int(lap) in pace['clean_laps'] else ''}"
                      for lap, t in sorted(pace["lap_times_s"].items(), key=lambda kv: int(kv[0])))
    out += [
        f"**Pace** — best {_fmt_time(pace['best_s'])} (lap {pace['best_lap']}), clean average "
        f"{_fmt_time(pace['clean_mean_s'])} ±{pace['clean_std_s']:.2f}s over "
        f"{len(pace['clean_laps'])} clean of {pace['valid_laps']} valid laps."
        + (f" Top speed {_speed(pace['top_speed_mps'])}." if pace.get("top_speed_mps") else ""),
        "",
        f"Lap times (* = clean): {times}",
        "",
        _pace_detail(pace),
        "",
    ]

    bal = e.get("balance")
    if bal:
        prev_bal = (prev or {}).get("balance") or {}
        prev_sd = prev_bal.get("steer_demand_deg", {})
        out += [
            "**Balance — steer demand** (steering-wheel degrees for a 100 m-radius arc; "
            "higher = more understeer. Brackets: change vs previous session.)",
            "",
            _measured_note(pace),
            "",
            "| Speed band | Entry (braking) | Mid (coasting) | Exit (throttle) |",
            "|---|---|---|---|",
        ]
        for name, low, high in SPEED_BANDS:
            cells = []
            for phase in PHASES:
                v = bal["steer_demand_deg"].get(name, {}).get(phase)
                pv = prev_sd.get(name, {}).get(phase)
                if v is None:
                    cells.append("—")
                elif pv is None:
                    cells.append(f"{v:.1f}")
                else:
                    cells.append(f"{v:.1f} ({v - pv:+.1f})")
            out.append(f"| {_band_label(name, low, high)} | " + " | ".join(cells) + " |")
        cs = bal["countersteer_per_lap"]
        out += [
            "",
            f"Countersteer events per lap (oversteer signal): entry {cs['entry']}, "
            f"mid {cs['mid']}, exit {cs['exit']}.",
            "",
        ]
        out += _equal_g_section(bal, prev_bal)
    out += _countersteer_events(e.get("countersteer_moments"))
    out += _corner_section(e, prev)

    tires = e.get("tires")
    if tires and tires.get("surface_c"):
        out += [
            "**Tyres** — surface temps averaged over the later clean laps (inner / middle / "
            f"outer, °{units['temp']}); hot pressure on the last clean lap",
            "",
            f"| Tyre | Inner | Middle | Outer | Hot pressure ({units['pressure']}) |",
            "|---|---|---|---|---|",
        ]
        for c in CORNERS:
            s = tires["surface_c"].get(c)
            if s:
                out.append(f"| {c} | {_t(s['inner'], units)} | {_t(s['middle'], units)} | "
                           f"{_t(s['outer'], units)} | {_p(tires['hot_pressure_kpa'].get(c), units)} |")
        snap = tires.get("pit_snapshot")
        if snap and snap.get("carcass_c"):
            out += ["", "Pit-in snapshot — carcass temps (inner / middle / outer) and tread used:", ""]
            for c in CORNERS:
                ct = snap["carcass_c"].get(c)
                wu = snap["tread_used_pct"].get(c)
                if ct:
                    wear = (f"; tread used {wu['inner']:.1f} / {wu['middle']:.1f} / "
                            f"{wu['outer']:.1f} %") if wu else ""
                    out.append(f"- {c}: {_t(ct['inner'], units)} / {_t(ct['middle'], units)} / "
                               f"{_t(ct['outer'], units)} °{units['temp']}{wear}")
        out.append("")

    plat = e.get("platform")
    if plat and plat.get("min_ride_height_mm"):
        rh = plat["min_ride_height_mm"]
        at = plat.get("ride_height_at_speed_mm", {})
        out += [
            f"**Platform** ({units['length']}) — minimum ride height (1st percentile): "
            + ", ".join(f"{c} {_l(rh.get(c), units)}" for c in CORNERS if c in rh)
            + (f". At speed: front {_l(at.get('front'), units)}, rear {_l(at.get('rear'), units)}, "
               f"rake {_l(plat.get('rake_at_speed_mm'), units)}" if at else "")
            + ".",
            "",
        ]
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Agent guide and notes template
# ═════════════════════════════════════════════════════════════════════════════

ENGINEER_GUIDE = """\
# Race engineer instructions — Tenths setup notebook

_Maintained by Tenths and rewritten on update. Put the driver's preferences in
the per-track `.notes.md` files instead of editing this one._

You are acting as a race engineer. The driver will ask for a setup for a car and
track, usually with a goal preset. Everything you know about how THIS driver and
car behave is in this folder. Tenths generated it from telemetry; it never
invents values.

## Read first
1. `<car>/<track>.md` for the track asked about — sessions, setups as driven, and
   how the car behaved on each.
2. `<car>/<track>.notes.md` — the driver's feel and the experiment log for this
   track: what was already tested and concluded.
2b. `<car>/car_notes.md` — what is known about this car across all tracks
   (how it responds to each adjustment). Start from it on a new track.
3. `<car>/limits.json` if it exists — garage ranges, steps and options. Never
   recommend a value outside min/max. Entries with `"linked": true` (ride height,
   camber, toe, bump rubber gap) have legal limits that move with other settings:
   change them in small steps and tell the driver to check the garage for red
   "Too Low / Too High" warnings. `"notes"` holds the car's own garage guidance
   (e.g. aero ride-height targets) and `"guide"` the car manual's cause-and-effect
   rules for each adjustment — use both, and say which you relied on.
4. Other `<car>/*.md` notebooks — carry over what generalises (dampers, diff,
   tyre behaviour), not track-specific aero or ride height.

## Goal presets
- **Fastest** — minimum single-lap time. Accept a car that is harder to drive
  and wears tyres faster. Qualifying and short races.
- **Balanced** (default) — race pace. Lap time first, but not at the cost of a
  car the driver cannot repeat lap after lap; favour a lower clean-lap spread.
- **Stable** — consistency and confidence. Minimise countersteer events and
  lap spread, keep the rear planted on entry, spare the tyres. Long races,
  night, rain, or an unfamiliar track.

## How to read the data
- **Balance at equal lateral g** — the table to compare sessions with. Steer
  demand (degrees for a 100 m arc; higher = more understeer) by speed band and
  lateral g, off the brake. A faster driver spends more time at high g, which
  needs more lock on ANY car, so never compare the phase table across sessions
  when driving intensity differs. The absolute value depends on the car; only
  differences mean anything.
- **Noise floor** — how far those numbers moved between sessions with no setup
  change. A setup change must move them by clearly more than the median before
  you call it an effect. Cells with few samples (n shown when too thin) are not
  evidence.
- **Countersteer moments** — every slide of 0.25 s or longer with its lap,
  corner and phase, including off/crash laps. A moment that repeats at the same
  corner across sessions is a car or line trait at that corner; a single long
  one is usually the incident the driver remembers.
- **A/B/A tests** — drift-corrected effects for baseline/change/baseline
  sequences. This is the strongest evidence the notebook has; prefer it over a
  plain before/after comparison.
- **Pace** — clean average, the average on settled laps, and the lap-time
  trend. A strongly negative trend means the driver was still learning: do not
  credit that pace to the setup.
- **Countersteer events per lap** — the oversteer signal, split by entry, mid
  and exit.
- Balance and platform exclude tyre warm-up laps; each session says which laps
  were measured. Few measured laps means rough numbers.
- **Clean-lap spread** — lap-to-lap consistency; a setup that is fast but raises
  spread is not a Balanced answer.
- **Tyres** — inner/middle/outer surface temps (camber and pressure), hot
  pressures, and pit-in carcass temps and tread used. Check the "still rising"
  flag before trusting pressures.
- **Platform** — minimum ride height and rake at speed. A minimum near zero
  means the car is bottoming.
- **In-car settings** — brake bias, TC, ABS and throttle map as DRIVEN, which
  can differ from the garage snapshot.
- Separate driver from car: a behaviour repeated on every clean lap in similar
  corners is the car; one-offs are the driver.
- Confirm the change was actually made. The session's "Changes vs previous"
  must list exactly the intended change; a setup name is not proof (on
  2026-09-25 `ra_wing5.sto` was saved with the wing unchanged). The driver can
  also export the setup from the garage (File Actions > Export) for you to check
  before they drive.
- Hold conditions: note track temperature for every comparison; a 10 °C swing
  changed the car more than the setup changes tested that day.

## Keep the experiment log
The notebook records what happened; it does not record what was being tested or
what was concluded. After every test, append an entry to the track's
`.notes.md` under `## Experiment log`, newest last, in this form:

    ### YYYY-MM-DD — <setup name>: <one change>
    - Hypothesis: <what the data showed and why this change should help>
    - Decision rule: <the result that keeps it, set BEFORE driving>
    - Result: <numbers from the notebook, vs baseline and the noise floor>
    - Verdict: kept / reverted / inconclusive — <one line why>
    - Learned: <what this says about the car or driver, beyond this track>

Read every earlier entry before recommending: never re-run a test that was
already ruled out unless conditions differ materially, and say so if they do.

If the lesson is about the car rather than the track ("softer front ARB made
the rear loose on entry"), also add one line under "How the car responds to
changes" in `<car>/car_notes.md`, citing the track and date. When the same
trait shows up at a second track, record it under "Traits seen at more than
one track".

## Test protocol: A/B/A
When the driver is working on a setup (not every session):

1. **A** — the current setup, unchanged, in today's conditions.
2. **B** — one change (two only if they act on clearly different things).
3. **A again** — the current setup once more, same conditions.

The repeat baseline measures how far the track and the driver drifted during
the test (on 2026-09-25 the track warmed 19 °F and the driver found 1.6 s
between two runs of the same setup). The notebook detects this sequence and
reports each result as *effect (drift)*: effect = B minus the average of the
two A runs. Judge the change on the effect, and only when it is larger than
both the drift and the noise floor. If the driver cannot run the second A,
say the verdict is provisional.

Set the decision rule before the driver runs B, and write it into the
experiment log.

## Order of work and when to stop
Work through the setup in this order, finishing one stage before the next,
because each stage changes what the later ones need:

1. Aero — wing and ride heights at speed against the car's targets
   (limits.json notes).
2. Anti-roll bars — overall balance.
3. Springs and bump rubbers — platform vs mechanical grip.
4. Dampers.
5. In-car electronics — brake bias, TC, ABS, throttle map.
6. Differential.
7. Alignment — camber, toe; tyre temperatures and wear.

Skip a stage when the data shows nothing to fix there; say so in the log.
Stop and declare the setup done when any of these holds:
- two consecutive tests show no effect larger than the drift and noise floor;
- the remaining candidate changes all have low expected impact;
- the driver is satisfied with the car.

When you stop, write a short summary in the experiment log: the final setup,
what was tested, and what was learned. Say plainly when remaining gains are
in the driving rather than the car.

## What to return
1. A short diagnosis citing the notebook: session numbers and values.
2. A change list the driver can type into the garage, in the units the
   notebook shows: `Section > Setting: current -> new — reason`. Converted
   imperial values can differ from the garage by one in the last digit
   (1028 vs 1029 lbs/in); the driver picks the nearest garage step.
3. Change one or two things per run so the next session shows what each did.
   If the goal needs more, give a sequence of runs.
4. What to look for in the next session's notebook entry to confirm or undo it.
5. Say so plainly when there is not enough data (one session, few clean laps,
   tyres not up to temperature). Suggest the experiment that would decide it.

## Rules
- Only recommend settings that appear in the notebook's setup tables. Do not
  invent setting names.
- Without `limits.json`, stay within or one step beyond the values already run,
  and label anything beyond them "untested — change this alone".
- Do not claim a change will gain a specific lap time unless the notebook shows
  it did before.
- Never ask for or produce a .sto file; the driver saves the setup in the garage.
"""

_NOTES_TEMPLATE = """\
# Driver notes — {car} at {track}

Your own observations, in any form. Tenths never overwrites this file; the race
engineer reads it alongside the notebook. Date each note and name the setup.

<!-- Example:
- 2026-09-25, lemans.sto: snappy on entry to T10a; car felt lazy through the esses.
-->
"""


_CAR_NOTES_TEMPLATE = """# Car notes — {car}

Lessons about this CAR that hold across tracks: how it responds to each
adjustment for this driver, and behaviours seen at more than one track.
Track-specific results stay in each track's `.notes.md` experiment log.
Tenths never overwrites this file.

## How the car responds to changes

<!-- - YYYY-MM-DD <track>: <change> -> <measured effect>. Source: <track> experiment log. -->

## Traits seen at more than one track

## Driver preferences
"""


def ensure_engineer_guide(root=None):
    """Write ENGINEER.md at the notebook root. Tenths owns it and keeps it current;
    driver preferences belong in the per-track notes files."""
    path = os.path.join(root or config.NOTEBOOK_DIR, "ENGINEER.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    current = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            current = f.read()
    if current != ENGINEER_GUIDE:
        _write_text(path, ENGINEER_GUIDE)
    return path


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def _all_ibt_files():
    files = []
    for folder in (config.TELEMETRY_ROOT, config.ARCHIVE_DIR):
        if os.path.isdir(folder):
            files += [os.path.join(folder, f) for f in os.listdir(folder)
                      if f.lower().endswith(".ibt")]
    return sorted(files, key=os.path.basename)


def notebook_cli(args):
    usage = ("Usage:\n"
             "  tenths notebook                    List notebooks and where they live\n"
             "  tenths notebook add <file.ibt>     Add one session\n"
             "  tenths notebook rebuild [car]      Add every .ibt in telemetry + archive\n"
             "                                     (optionally only cars starting with [car])\n"
             "  tenths notebook limits <car>       Create a garage-limits template for a car")
    if args and args[0] in ("-h", "--help"):
        print(usage)
        return

    if not args:
        root = config.NOTEBOOK_DIR
        print(f"Setup notebook: {root}")
        print(f"Automatic capture: {'on' if config.notebook_enabled() else 'off'}")
        if not os.path.isdir(root):
            print("  (empty — run `tenths notebook rebuild` to add past sessions)")
            return
        for car in sorted(os.listdir(root)):
            folder = os.path.join(root, car)
            if os.path.isdir(folder):
                for name in sorted(os.listdir(folder)):
                    if name.endswith(".json") and name != "limits.json":
                        n = len(load_notebook(os.path.join(folder, name)).get("entries", []))
                        print(f"  {car}/{name[:-5]}.md  ({n} session{'s' if n != 1 else ''})")
        return

    command, rest = args[0], args[1:]
    if command == "add":
        path = " ".join(rest).strip('"')
        if not os.path.isfile(path):
            print(f"File not found: {path}")
            return
        written = record_session(path)
        print(f"Updated: {written}" if written else "Nothing to record for that session.")
    elif command == "rebuild":
        prefix = rest[0].lower() if rest else ""
        files = [f for f in _all_ibt_files() if os.path.basename(f).lower().startswith(prefix)]
        print(f"Adding {len(files)} session(s) to the setup notebook...")
        updated = set()
        for path in files:
            try:
                written = record_session(path)
            except Exception as exc:          # one bad file must not stop the rebuild
                print(f"  FAILED {os.path.basename(path)}: {exc}")
                continue
            if written:
                updated.add(written)
                print(f"  added  {os.path.basename(path)}")
            else:
                print(f"  skip   {os.path.basename(path)}")
        print(f"Done. {len(updated)} notebook(s) updated under {config.NOTEBOOK_DIR}")
    elif command == "limits":
        if not rest:
            print("Usage: tenths notebook limits <car>   (e.g. fordmustanggt3)")
            return
        path, created = write_limits_template(rest[0])
        print(f"{'Created' if created else 'Already exists'}: {path}")
    else:
        print(usage)
