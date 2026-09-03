"""
iRacing .ibt → Full Coaching Report (Single Command)
======================================================
Parses .ibt directly, normalizes units, filters invalid laps,
and produces a complete coaching report.

Usage:
    python analyze_ibt.py "path\\to\\file.ibt"
    python analyze_ibt.py                        # finds largest .ibt in telemetry root

Requirements:
    python -m pip install pyirsdk pandas
"""

import os
import sys
import glob
import irsdk
import pandas as pd
import numpy as np

from tenths.units import celsius_to_fahrenheit, mph_to_mps, mps_to_mph

# ── Config ────────────────────────────────────────────────────────────────────
COACHING_CHANNELS = [
    "Lap", "LapCurrentLapTime", "LapDistPct", "LapDist", "LapDeltaToBestLap",
    "LapLastLapTime", "LapBestLapTime", "LapDeltaToOptimalLap", "LapCompleted",
    "Speed", "RPM", "Gear", "Throttle", "Brake", "SteeringWheelAngle",
    "BrakeABSactive", "BrakeABScutPct",
    "LFbrakeLinePress", "RFbrakeLinePress", "LRbrakeLinePress", "RRbrakeLinePress",
    "LongAccel", "LatAccel", "VertAccel", "YawRate", "Roll", "Pitch",
    "Lat", "Lon",
    "LFtempM", "LFtempL", "LFtempR", "RFtempM", "RFtempL", "RFtempR",
    "LRtempM", "LRtempL", "LRtempR", "RRtempM", "RRtempL", "RRtempR",
    "LFwearM", "RFwearM", "LRwearM", "RRwearM",
    "LFpressure", "RFpressure", "LRpressure", "RRpressure",
    "FuelLevelPct",
]

LOAD_LAT_G = 0.5
LOAD_LONG_G = 0.3

# Absolute speed gates behind the class-specific coaching notes. These were
# authored as mph literals inline; they are named and expressed in SI here so
# the analysis pipeline can carry m/s throughout. Values are unchanged.
OVER_SLOWING_MIN_SPEED_MPS = mph_to_mps(20.0)   # 20 mph — "Over-slowing"
LUGGING_MIN_SPEED_MPS = mph_to_mps(40.0)        # 40 mph — "Lugging"
# Below this apex speed, full throttle is trivial, so exit metrics are skipped.
EXIT_METRICS_MIN_APEX_MPS = mph_to_mps(30.0)    # 30 mph

# Trail-braking zone diagnostic (see diagnose_trail_zone). Thresholds validated
# against 469 trail zones from 40+ archived sessions across four car models
# (Mustang GT3, Ferrari 296 GT3/Challenge, BMW M4 GT3), 2026-09.
#
# The old rule `yaw > 0.5 and brake > 20 -> "High yaw — oversteer risk"` fired on
# 87 of those 469 zones (19%), and every one was a false positive: an advanced
# driver rotating the car on the brake at high lateral load, which the ARA
# framework (SimCoach/CONTEXT.md) calls neutral steer / the three tools of
# rotation — good technique, not instability. High yaw at high lateral G is a
# consequence of corner speed, not the rear stepping out. Raw yaw rate alone was
# never a valid oversteer signal, and steering *rate* (the signal the earlier
# spec proposed to rescue it) is too noisy at 60 Hz to use — single-sample spikes
# of 20-67 rad/s made the yaw/steering ratio meaningless. So the diagnosis is
# reframed around lateral G, which is robust:
#   - high lat-G + high yaw + brake on -> controlled high-speed rotation (good)
#   - LOW lat-G + high yaw + brake on  -> genuine oversteer signature (rear out
#     below the grip limit). None occurred on the clean best laps measured, so
#     this is a rare-event guard, kept conservative.
COMBINED_LOAD_LAT_G = 1.0       # lateral load that confirms the car is cornering,
                                # not braking in a straight line. Set at 1.0 G so
                                # the two ~1.1 G clean-lap zones that would
                                # otherwise read as "oversteer" are correctly
                                # treated as loaded rotation; a genuine low-speed
                                # spin sits well below this.
# Minimum brake % for a zone to count as still braking. The old rule required
# 30% before it would call a zone well-driven, so a driver releasing the brake
# progressively into the corner — correct technique — fell through to the yaw
# check and got flagged. 15% keeps light trail-brake pressure in the loaded case.
TRAIL_BRAKE_MIN_PCT = 15.0
# Chooses the LABEL for a loaded zone: at or above this lateral G a high yaw
# reading is described as high-speed rotation rather than plain combined load.
# It does not gate the oversteer branch — any zone at or above
# COMBINED_LOAD_LAT_G is already treated as loaded and never called oversteer.
HIGH_G_ROTATION_LAT_G = 1.3
# Yaw that counts as high for labelling purposes (p50 of measured zones is
# 0.53 rad/s, so this is "more rotation than the typical corner").
OVERSTEER_YAW_RATE = 0.5        # rad/s
# Rotation this fast is abnormal for a clean lap at any lateral load, so it is
# checked before the load and braking-straight branches — otherwise a genuine
# spin under heavy braking reads as "Braking straight", and a big moment in the
# 1.0-1.3 G band reads as "Good". Measured ceiling across the 469 zones is
# 1.03 rad/s (p99 = 0.88), so 1.2 fires on none of them and only catches
# genuinely abnormal rotation.
ABNORMAL_YAW_RATE = 1.2         # rad/s
BRAKING_STRAIGHT_BRAKE_PCT = 60.0
BRAKING_STRAIGHT_LAT_G = 0.5


def diagnose_trail_zone(brake_pct, lateral_g, yaw_rate):
    """Classify one trail-braking zone from its brake %, peak lateral G and peak
    yaw rate. Single source of truth for both the console dump
    (trail_braking_analysis) and the report data (_extract_trail_braking).

    Units: brake_pct is 0-100, lateral_g is |LatAccel| in G, yaw_rate is
    |YawRate| in rad/s. All three are per-zone aggregates (brake mean, lat/yaw
    peak) computed by the callers.

    Returns a short diagnosis string. See the constants above for the validation
    behind each branch and why steering rate is deliberately not used.
    """
    # Missing or non-finite telemetry must never manufacture a warning. Without
    # this, NaN fails every comparison, falls through to the oversteer branch and
    # reports instability for a zone we have no lateral data for.
    if not (np.isfinite(brake_pct) and np.isfinite(lateral_g)
            and np.isfinite(yaw_rate)):
        return "Light trail"

    # Abnormally fast rotation, regardless of lateral load. Checked first so a
    # spin is not absorbed by the "braking straight" or "combined load" branches
    # below. See ABNORMAL_YAW_RATE for the measured ceiling this sits above.
    if yaw_rate >= ABNORMAL_YAW_RATE and brake_pct > TRAIL_BRAKE_MIN_PCT:
        return "Oversteer risk — rear rotating beyond corner load"

    # Loaded and braking: the car is cornering with the brake on. High yaw here
    # is rotation, not instability — reported as such rather than "oversteer".
    if lateral_g >= COMBINED_LOAD_LAT_G and brake_pct > TRAIL_BRAKE_MIN_PCT:
        if lateral_g >= HIGH_G_ROTATION_LAT_G and yaw_rate > OVERSTEER_YAW_RATE:
            return "High-speed rotation — normal for this corner speed"
        return "Good — combined load"
    # Hard braking with almost no lateral load: braking in a straight line.
    if brake_pct > BRAKING_STRAIGHT_BRAKE_PCT and lateral_g < BRAKING_STRAIGHT_LAT_G:
        return "Braking straight"
    # High yaw with the brake on but WITHOUT cornering load — the rear is
    # rotating beyond what corner speed accounts for. This is the real oversteer
    # signature and the only case that keeps the warning.
    if yaw_rate > OVERSTEER_YAW_RATE and brake_pct > TRAIL_BRAKE_MIN_PCT:
        return "Oversteer risk — rear rotating beyond corner load"
    return "Light trail"

# Car class detection — GT4 cars have high-downforce physics requiring
# different braking shape (spike initial brake) and faster downshifts
GT4_CARS = ["bmwm4evogt4", "bmwm4gt4", "amg_gt4", "porsche718gt4", "mclarengt4"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_time(s):
    if s <= 0:
        return "N/A"
    return f"{int(s//60)}:{s%60:06.3f}"


def parse_session_info(filepath):
    """
    Parse the session info YAML header from an .ibt file.
    Returns metadata dict with car name, track name, event type, etc.
    No pyirsdk needed — reads the raw binary header directly.
    """
    import struct
    import yaml

    with open(filepath, 'rb') as f:
        header = f.read(112)
        _, _, _ = struct.unpack_from('iii', header, 0)  # ver, status, tick_rate
        _, session_info_len, session_info_offset = struct.unpack_from('iii', header, 12)

        f.seek(session_info_offset)
        session_info_raw = f.read(session_info_len)
        session_info_str = session_info_raw.decode('latin-1').rstrip('\x00')
        info = yaml.safe_load(session_info_str)

    if not info:
        return {}

    wi = info.get('WeekendInfo', {})
    di = info.get('DriverInfo', {})

    # Find the player's car in the Drivers list
    driver_idx = di.get('DriverCarIdx', -1)
    drivers = di.get('Drivers', [])
    player_car = {}
    for d in drivers:
        if d.get('CarIdx') == driver_idx:
            player_car = d
            break

    return {
        # Track info
        'track_display_name': wi.get('TrackDisplayName', ''),
        'track_config_name': wi.get('TrackConfigName', ''),
        'track_id': wi.get('TrackID', 0),
        'track_name_internal': wi.get('TrackName', ''),
        'track_length_km': wi.get('TrackLength', ''),
        'track_num_turns': wi.get('TrackNumTurns', 0),
        'track_city': wi.get('TrackCity', ''),
        'track_state': wi.get('TrackState', ''),
        'track_country': wi.get('TrackCountry', ''),
        'track_pit_speed_kph': wi.get('TrackPitSpeedLimit', ''),
        'track_lat': wi.get('TrackLatitude', ''),
        'track_lon': wi.get('TrackLongitude', ''),
        # Car info
        'car_screen_name': player_car.get('CarScreenName', ''),
        'car_screen_name_short': player_car.get('CarScreenNameShort', ''),
        'car_path': player_car.get('CarPath', ''),
        'car_id': player_car.get('CarID', 0),
        'car_class_short': player_car.get('CarClassShortName', ''),
        'car_class_id': player_car.get('CarClassID', 0),
        # Driver info
        'driver_name': player_car.get('UserName', ''),
        'driver_id': di.get('DriverUserID', 0),
        'driver_car_redline': di.get('DriverCarRedLine', 0),
        'driver_car_idle_rpm': di.get('DriverCarIdleRPM', 0),
        'driver_gearbox_type': di.get('DriverGearboxType', ''),
        'driver_car_fuel_max_ltr': di.get('DriverCarFuelMaxLtr', 0),
        # Session info
        'event_type': wi.get('EventType', ''),
        'series_id': wi.get('SeriesID', 0),
        'season_id': wi.get('SeasonID', 0),
        'session_id': wi.get('SessionID', 0),
        'subsession_id': wi.get('SubSessionID', 0),
        'official': wi.get('Official', 0),
        'race_week': wi.get('RaceWeek', 0),
        # Weather
        'track_temp_c': wi.get('TrackSurfaceTemp', ''),
        'air_temp_c': wi.get('TrackAirTemp', ''),
        'humidity_pct': wi.get('TrackRelativeHumidity', ''),
    }

def parse_ibt(filepath):
    """Parse .ibt file and return normalized DataFrame."""
    ibt = irsdk.IBT()
    ibt.open(filepath)

    available = [ch for ch in COACHING_CHANNELS if ch in ibt.var_headers_names]

    data = {}
    for ch in available:
        try:
            values = ibt.get_all(ch)
            if values is not None:
                data[ch] = values
        except Exception:
            pass

    # Derive sample rate
    sample_rate = 60
    if 'SessionTime' in ibt.var_headers_names:
        try:
            st = ibt.get_all('SessionTime')
            if st and len(st) > 1:
                dt = st[1] - st[0]
                if dt > 0:
                    sample_rate = round(1.0 / dt)
        except Exception:
            pass

    ibt.close()

    df = pd.DataFrame(data)

    # Unit normalization (iRacing .ibt native units → coaching units)
    for col in ['Throttle', 'Brake']:
        if col in df.columns:
            df[col] = df[col] * 100.0
    for col in ['LatAccel', 'LongAccel', 'VertAccel']:
        if col in df.columns:
            df[col] = df[col] / 9.80665
    if 'FuelLevelPct' in df.columns:
        df['FuelLevelPct'] = df['FuelLevelPct'] * 100.0
    if 'BrakeABScutPct' in df.columns:
        df['BrakeABScutPct'] = df['BrakeABScutPct'] * 100.0
    if 'LapDistPct' in df.columns:
        df['LapDistPct'] = df['LapDistPct'] * 100.0

    # Parse metadata from filename
    basename = os.path.splitext(os.path.basename(filepath))[0]
    parts = basename.split('_', 1)
    vehicle = parts[0] if parts else "Unknown"
    venue = parts[1].split(' ')[0] if len(parts) > 1 else "Unknown"

    return df, sample_rate, vehicle, venue

def get_valid_laps(df):
    """Return list of valid complete driving laps."""
    laps = df.groupby('Lap').agg(
        MaxSpeed=('Speed', 'max'),
        LapTime=('LapLastLapTime', 'max'),
        MaxDistPct=('LapDistPct', 'max'),
        MinDistPct=('LapDistPct', 'min'),
        Samples=('Speed', 'count'),
        AvgSpeed=('Speed', 'mean'),
    )
    # Valid lap criteria:
    # - Max speed > 31mph (13.9 m/s)
    # - Track coverage: started below 10% AND reached above 90%
    # - Has a lap time > 0
    # - Has enough samples (>500 at 60Hz)
    # - Average speed > 10 m/s (22mph)
    # - Not the final lap if it has a braking zone ending at 0mph near end of track
    valid = laps[
        (laps['MaxSpeed'] > 13.9) &
        (laps['MinDistPct'] < 10) &
        (laps['MaxDistPct'] > 90) &
        (laps['LapTime'] > 0) &
        (laps['Samples'] > 500) &
        (laps['AvgSpeed'] > 10)
    ]

    # Additional check: exclude laps where the car stops (speed=0) mid-lap
    # (indicates session end or reset)
    valid_list = []
    for lap in valid.index:
        lap_data = df[df['Lap'] == lap]
        # Check if car reaches 0 speed after being above 50mph
        speeds = lap_data['Speed'].values
        was_fast = False
        stopped_after_fast = False
        for spd in speeds:
            if spd > 13.9:
                was_fast = True
            if was_fast and spd < 0.5:
                stopped_after_fast = True
                break
        if not stopped_after_fast:
            valid_list.append(lap)

    return valid_list

# ── Analysis Functions ────────────────────────────────────────────────────────
def lap_summary(df, valid_laps):
    print("\n" + "=" * 65)
    print("LAP SUMMARY")
    print("=" * 65)

    results = []
    for lap in valid_laps:
        ld = df[df['Lap'] == lap]
        time = ld['LapLastLapTime'].iloc[-1]
        abs_hits = int(ld['BrakeABSactive'].sum())
        max_spd = mps_to_mph(ld['Speed'].max())
        avg_thr = ld['Throttle'].mean()
        avg_brk = ld['Brake'].mean()
        results.append({'Lap': lap, 'Time': time, 'ABS': abs_hits,
                       'MaxSpd': max_spd, 'Thr': avg_thr, 'Brk': avg_brk})

    # Filter out laps with invalid times (-1 or 0) for best/worst selection
    valid_results = [r for r in results if r['Time'] > 0]
    if not valid_results:
        print("  No laps with valid times found.")
        return None, None

    best_lap = min(valid_results, key=lambda x: x['Time'])['Lap']
    worst_lap = max(valid_results, key=lambda x: x['Time'])['Lap']

    for r in results:
        if r['Time'] <= 0:
            continue  # skip laps without valid times in output
        marker = " <-- BEST" if r['Lap'] == best_lap else (" <-- WORST" if r['Lap'] == worst_lap else "")
        print(f"  Lap {r['Lap']:>2}: {fmt_time(r['Time'])}  ABS={r['ABS']:>4}  "
              f"MaxSpd={r['MaxSpd']:.0f}mph  Thr={r['Thr']:.0f}%  Brk={r['Brk']:.0f}%{marker}")

    return best_lap, worst_lap

# Physics profiles used for coaching diagnostics. These are NOT iRacing car
# classes — they select which braking/shifting rules apply.
#
# GT4 has validated thresholds (spike the pedal while downforce is high, fast
# downshifts, early brake release to rotate). Everything else uses GENERIC.
#
# Previously the fallback was called "Touring", which meant a Ferrari 296 GT3 was
# both labelled Touring in the report and judged against Touring-specific
# thresholds it was never validated for. Naming it GENERIC is honest: it says
# "no class-specific rules yet" rather than asserting the wrong ones.
PROFILE_GT4 = "GT4"
PROFILE_GENERIC = "Generic"

# iRacing CarClassShortName values known to use GT4 physics
GT4_CLASS_NAMES = ("gt4",)


def detect_car_class(vehicle, car_class_short=None):
    """Select the physics profile for coaching diagnostics.

    Args:
        vehicle: car slug from the .ibt filename
        car_class_short: iRacing's CarClassShortName from the session info,
                        preferred when available

    Returns PROFILE_GT4 or PROFILE_GENERIC.
    """
    if car_class_short:
        normalized = str(car_class_short).lower().replace(' ', '')
        if any(name in normalized for name in GT4_CLASS_NAMES):
            return PROFILE_GT4
        # A known class that is not GT4 gets generic rules, not Touring's.
        return PROFILE_GENERIC

    vehicle_lower = (vehicle or '').lower().replace(' ', '').replace('-', '')
    for gt4 in GT4_CARS:
        if gt4 in vehicle_lower:
            return PROFILE_GT4
    return PROFILE_GENERIC


def _is_human_readable_class(value):
    """True if a CarClassShortName looks like a label rather than a slug.

    iRacing is inconsistent here. Some sessions report a proper class name
    ("GT3 Class", "BMW M2 CS Racing"), others report an internal slug
    ("bmwm4evogt4"). A slug must not be shown to the driver.
    """
    text = str(value).strip()
    if not text:
        return False
    return ' ' in text or any(char.isupper() for char in text)


def display_car_class(session_info, physics_profile=None):
    """The car class to show the user.

    iRacing's own CarClassShortName ("GT3 Class") is what a driver recognises,
    but only when it is a real label — see _is_human_readable_class. Falls back
    to the physics profile otherwise.
    """
    class_short = (session_info or {}).get('car_class_short')
    if class_short and _is_human_readable_class(class_short):
        return str(class_short).strip()
    return physics_profile or PROFILE_GENERIC


def braking_analysis(df, lap_num, vehicle="Unknown"):
    print(f"\n{'='*65}")
    car_class = detect_car_class(vehicle)
    print(f"BRAKING ZONES — Lap {lap_num} [{car_class} physics]")
    print(f"{'='*65}")

    lap = df[df['Lap'] == lap_num].copy()
    lap = lap.reset_index(drop=True)
    sample_rate = 60  # Hz

    braking = lap[lap['Brake'] > 50][['LapDistPct','Speed','Brake','BrakeABSactive']].copy()
    if braking.empty:
        print("  No braking zones found.")
        return
    braking['zone'] = (braking['LapDistPct'].diff().abs() > 5).cumsum()

    has_gear = 'Gear' in lap.columns and lap['Gear'].max() > 0

    if has_gear:
        if car_class == "GT4":
            print(f"  {'Pos':>6} {'Entry':>8} {'Min':>7} {'MaxBrk':>7} {'ABS':>5} "
                  f"{'T2Peak':>7} {'Coast':>6} {'TInBrk':>7} {'ApxBrk':>7}  Notes")
            print(f"  {'-'*105}")
        else:
            print(f"  {'Pos':>6} {'Entry':>8} {'Min':>7} {'MaxBrk':>7} {'ABS':>5} "
                  f"{'Brk2Shft':>9} {'MaxDS_RPM':>10} {'ApexRPM':>8}  Notes")
            print(f"  {'-'*95}")
    else:
        print(f"  {'Pos':>6} {'Entry':>8} {'Min':>7} {'MaxBrk':>8} {'ABS':>5}")
        print(f"  {'-'*45}")

    for z, grp in braking.groupby('zone'):
        pos = grp['LapDistPct'].mean()
        # SI internally so the shared note thresholds apply; converted at print.
        entry = grp['Speed'].iloc[0]
        min_spd = grp['Speed'].min()
        max_brk = grp['Brake'].max()
        abs_h = int(grp['BrakeABSactive'].sum())
        flag = " [ABS]" if abs_h > 0 else ""

        if not has_gear:
            print(f"  {pos:5.1f}% {mps_to_mph(entry):>7.0f}mph "
                  f"{mps_to_mph(min_spd):>6.0f}mph {max_brk:>7.0f}% {abs_h:>5}{flag}")
            continue

        # Gear shifting diagnostics
        # Get the full lap data for this zone's track position range
        zone_start = grp['LapDistPct'].min() - 2
        zone_end = grp['LapDistPct'].max() + 5  # extend past braking into corner
        zone_full = lap[(lap['LapDistPct'] >= zone_start) & (lap['LapDistPct'] <= zone_end)].copy()

        # 1. Brake-to-Shift Delta
        brake_start_idx = zone_full[zone_full['Brake'] > 10].index.min()
        gear_changes = zone_full[zone_full['Gear'].diff() < 0]  # downshifts
        if brake_start_idx is not None and not gear_changes.empty:
            first_ds_idx = gear_changes.index.min()
            brake_to_shift = (first_ds_idx - brake_start_idx) / sample_rate
        else:
            brake_to_shift = None

        # 2. Max Downshift RPM (highest RPM within 0.5s after any downshift)
        max_ds_rpm = 0
        if not gear_changes.empty:
            for ds_idx in gear_changes.index:
                window_end = ds_idx + int(0.5 * sample_rate)
                window = lap.loc[ds_idx:min(window_end, lap.index.max())]
                if 'RPM' in window.columns and not window.empty:
                    rpm_val = window['RPM'].max()
                    if rpm_val > max_ds_rpm:
                        max_ds_rpm = rpm_val

        # 3. Apex RPM (RPM at minimum speed point)
        min_speed_idx = zone_full['Speed'].idxmin()
        apex_rpm = zone_full.loc[min_speed_idx, 'RPM'] if 'RPM' in zone_full.columns else 0

        # 4. Apex Brake Pressure (brake % at minimum speed point)
        apex_brake = zone_full.loc[min_speed_idx, 'Brake'] if 'Brake' in zone_full.columns else 0

        # 5. Time to Peak Brake (GT4-specific: time from >5% to peak pressure)
        time_to_peak = None
        # Find the start of THIS braking event (brake rises from <5% to >5%)
        # Use the zone_full data but ensure we find the initial application, not residual trail
        zone_brake_series = zone_full['Brake']
        # Find first sample where brake is below 5% (off-brake), then first above 5% after that
        off_brake = zone_full[zone_full['Brake'] < 5]
        if not off_brake.empty:
            search_start = off_brake.index.min()
            after_release = zone_full.loc[search_start:]
            brake_initial_idx = after_release[after_release['Brake'] > 5].index.min()
        else:
            # No off-brake samples — use first >5% in zone
            brake_initial_idx = zone_full[zone_full['Brake'] > 5].index.min()
        if brake_initial_idx is not None and not pd.isna(brake_initial_idx):
            # Find peak brake after initial application
            zone_brake_data = zone_full.loc[brake_initial_idx:]
            if not zone_brake_data.empty:
                peak_idx = zone_brake_data['Brake'].idxmax()
                time_to_peak = (peak_idx - brake_initial_idx) / sample_rate

        # 6. Late-Zone ABS Detection (GT4-specific)
        late_abs = False
        if abs_h > 2:
            zone_abs_data = grp[grp['BrakeABSactive'] > 0]
            if not zone_abs_data.empty:
                zone_midpoint = (grp['LapDistPct'].min() + grp['LapDistPct'].max()) / 2
                late_abs_hits = len(zone_abs_data[zone_abs_data['LapDistPct'] > zone_midpoint])
                early_abs_hits = len(zone_abs_data[zone_abs_data['LapDistPct'] <= zone_midpoint])
                late_abs = late_abs_hits > early_abs_hits

        # Diagnostic flags — car-class-specific
        notes = []
        if abs_h > 0:
            notes.append("[ABS]")

        if car_class == "GT4":
            # GT4: spike the pedal immediately while downforce is highest
            if time_to_peak is not None and time_to_peak > 0.4:
                notes.append("Lazy Initial Brake")
            # GT4: ABS in second half means squeezing when aero grip is gone
            if late_abs:
                notes.append("Late Brake Squeeze")
            # GT4: stiff suspension needs early brake release to rotate
            if apex_brake > 15 and min_spd > OVER_SLOWING_MIN_SPEED_MPS:
                notes.append("Over-slowing (Trust GT4 Grip)")
            # GT4: fast downshifts are optimal for engine braking
            if brake_to_shift is not None and brake_to_shift >= 0 and brake_to_shift < 0.15:
                notes.append("Early Shift (Protection Risk)")
            if max_ds_rpm > 7500:
                notes.append("Over-rev Risk")
            if apex_rpm < 4000 and min_spd > LUGGING_MIN_SPEED_MPS:
                notes.append("Lugging")
        else:
            # Touring car (M2 CS, etc.) — original logic
            if brake_to_shift is not None and brake_to_shift >= 0 and brake_to_shift < 0.2:
                notes.append("Early Shift")
            if max_ds_rpm > 7000:
                notes.append("Aggressive Shift")
            if apex_rpm < 3500 and min_spd > LUGGING_MIN_SPEED_MPS:
                notes.append("Lugging")

        b2s_str = f"{brake_to_shift:.2f}s" if brake_to_shift is not None else "N/A"
        ds_rpm_str = f"{max_ds_rpm:.0f}" if max_ds_rpm > 0 else "N/A"
        notes_str = " ".join(notes) if notes else ""

        if car_class == "GT4":
            t2p_str = f"{time_to_peak:.2f}s" if time_to_peak is not None else "N/A"
            apx_brk_str = f"{apex_brake:.0f}%"

            # Coast Time calculation for print mode
            coast_time_val = None
            if brake_initial_idx is not None and not pd.isna(brake_initial_idx):
                pre_brake = lap.loc[max(0, int(brake_initial_idx) - int(2.0 * sample_rate)):int(brake_initial_idx)]
                if not pre_brake.empty and 'Throttle' in pre_brake.columns:
                    throttle_on = pre_brake[pre_brake['Throttle'] > 0]
                    if not throttle_on.empty:
                        thr_off_idx = throttle_on.index.max()
                        if lap.loc[thr_off_idx, 'Brake'] > 1:
                            coast_time_val = 0.0
                        else:
                            coast_time_val = (brake_initial_idx - thr_off_idx) / sample_rate
                            if coast_time_val < 0:
                                coast_time_val = 0.0
                    else:
                        coast_time_val = 0.0

            # Turn-In Brake % for print mode
            turnin_brk_val = None
            if 'SteeringWheelAngle' in zone_full.columns:
                steer_search = zone_full.loc[brake_initial_idx:] if brake_initial_idx is not None and not pd.isna(brake_initial_idx) else zone_full
                steering_commit = steer_search[steer_search['SteeringWheelAngle'].abs() > 0.2618]
                if not steering_commit.empty:
                    ti_idx = steering_commit.index.min()
                    turnin_brk_val = lap.loc[ti_idx, 'Brake'] if ti_idx in lap.index else None

            coast_str = f"{coast_time_val:.2f}s" if coast_time_val is not None else "N/A"
            turnin_str = f"{turnin_brk_val:.0f}%" if turnin_brk_val is not None else "N/A"

            print(f"  {pos:5.1f}% {mps_to_mph(entry):>7.0f}mph "
                  f"{mps_to_mph(min_spd):>6.0f}mph {max_brk:>6.0f}% {abs_h:>5} "
                  f"{t2p_str:>7} {coast_str:>6} {turnin_str:>7} {apx_brk_str:>7}  {notes_str}")
        else:
            print(f"  {pos:5.1f}% {mps_to_mph(entry):>7.0f}mph "
                  f"{mps_to_mph(min_spd):>6.0f}mph {max_brk:>6.0f}% {abs_h:>5} "
                  f"{b2s_str:>9} {ds_rpm_str:>10} {apex_rpm:>8.0f}  {notes_str}")

def tire_temp_analysis(df, lap_num):
    print(f"\n{'='*65}")
    print(f"TIRE TEMPS — Lap {lap_num} (under-load only)")
    print(f"{'='*65}")

    lap = df[df['Lap'] == lap_num]
    under_load = lap[
        (lap['LatAccel'].abs() >= LOAD_LAT_G) |
        (lap['LongAccel'].abs() >= LOAD_LONG_G)
    ]

    if len(under_load) < 50:
        print(f"  Not enough under-load samples ({len(under_load)})")
        return

    print(f"  Samples: {len(under_load)}")
    print(f"  {'Corner':<6} {'Inner':>7} {'Mid':>7} {'Outer':>7} {'Avg':>7}")
    print(f"  {'-'*40}")

    for corner, (ic, mc, oc) in [('LF',('LFtempL','LFtempM','LFtempR')),
                                   ('RF',('RFtempL','RFtempM','RFtempR')),
                                   ('LR',('LRtempL','LRtempM','LRtempR')),
                                   ('RR',('RRtempL','RRtempM','RRtempR'))]:
        if not all(c in under_load.columns for c in [ic, mc, oc]):
            continue
        i, m, o = under_load[ic].mean(), under_load[mc].mean(), under_load[oc].mean()
        # This is the legacy print path, so it formats °F directly.
        i_f, m_f, o_f = (celsius_to_fahrenheit(i), celsius_to_fahrenheit(m),
                         celsius_to_fahrenheit(o))
        avg_f = (i_f + m_f + o_f) / 3
        print(f"  {corner:<6} {i_f:>7.1f} {m_f:>7.1f} {o_f:>7.1f} {avg_f:>7.1f}")

def trail_braking_analysis(df, lap_num):
    print(f"\n{'='*65}")
    print(f"TRAIL BRAKING — Lap {lap_num}")
    print(f"{'='*65}")

    lap = df[df['Lap'] == lap_num].copy()
    trail = lap[
        (lap['Brake'] > 10) &
        (lap['SteeringWheelAngle'].abs() > 0.1)
    ][['LapDistPct','Brake','LatAccel','YawRate']].copy()

    if trail.empty:
        print("  No trail braking detected.")
        return

    trail['zone'] = (trail['LapDistPct'].diff().abs() > 5).cumsum()
    print(f"  {'Pos':>6} {'Brake':>7} {'LatG':>7} {'Yaw':>7}  Diagnosis")
    print(f"  {'-'*55}")

    for z, grp in trail.groupby('zone'):
        pos = grp['LapDistPct'].mean()
        brk = grp['Brake'].mean()
        lat = grp['LatAccel'].abs().max()
        yaw = grp['YawRate'].abs().max()
        diag = diagnose_trail_zone(brk, lat, yaw)
        print(f"  {pos:5.1f}% {brk:>6.0f}% {lat:>6.2f}G {yaw:>6.2f}  {diag}")

def abs_trend(df, valid_laps):
    print(f"\n{'='*65}")
    print("ABS TREND")
    print(f"{'='*65}")
    mid = len(valid_laps) // 2
    early = valid_laps[:mid] if mid > 0 else valid_laps
    late = valid_laps[mid:] if mid > 0 else valid_laps
    early_avg = np.mean([int(df[df['Lap']==l]['BrakeABSactive'].sum()) for l in early])
    late_avg = np.mean([int(df[df['Lap']==l]['BrakeABSactive'].sum()) for l in late])
    print(f"  First half ({early[0]}-{early[-1]}): {early_avg:.0f} ABS/lap avg")
    print(f"  Second half ({late[0]}-{late[-1]}): {late_avg:.0f} ABS/lap avg")
    print(f"  Trend: {late_avg - early_avg:+.0f}")

def track_position_map(df, lap_num):
    """Output GPS coordinates for braking zones and key track positions."""
    has_gps = 'Lat' in df.columns and 'Lon' in df.columns
    has_dist = 'LapDist' in df.columns
    if not has_gps and not has_dist:
        return  # silently skip if no position data available

    print(f"\n{'='*65}")
    print(f"TRACK POSITION MAP — Lap {lap_num}")
    print(f"{'='*65}")

    lap = df[df['Lap'] == lap_num].copy()
    lap = lap.reset_index(drop=True)

    # Track length from LapDist
    if has_dist:
        track_length = lap['LapDist'].max()
        print(f"  Track length: {track_length:.0f}m ({track_length/1609.34:.2f}mi)")

    # Braking zones with GPS
    braking = lap[lap['Brake'] > 50][['LapDistPct', 'Speed', 'Brake', 'BrakeABSactive']].copy()
    if has_gps:
        braking_full = lap[lap['Brake'] > 50][['LapDistPct', 'Lat', 'Lon']].copy()
    if braking.empty:
        return

    braking['zone'] = (braking['LapDistPct'].diff().abs() > 5).cumsum()
    if has_gps:
        braking_full['zone'] = (braking_full['LapDistPct'].diff().abs() > 5).cumsum()

    print(f"\n  Braking Zone Coordinates (brake entry point):")
    if has_gps and has_dist:
        print(f"  {'Pct':>6} {'Dist':>7} {'Lat':>11} {'Lon':>12} {'Entry':>7} {'MinSpd':>7}")
        print(f"  {'-'*60}")
    elif has_dist:
        print(f"  {'Pct':>6} {'Dist':>7} {'Entry':>7} {'MinSpd':>7}")
        print(f"  {'-'*35}")

    for z, grp in braking.groupby('zone'):
        pct = grp['LapDistPct'].iloc[0]  # entry point (first sample)
        entry_spd = mps_to_mph(grp['Speed'].iloc[0])
        min_spd = mps_to_mph(grp['Speed'].min())

        # Get GPS at brake entry point
        entry_idx = grp.index[0]
        dist_val = lap.loc[entry_idx, 'LapDist'] if has_dist else 0
        lat_val = lap.loc[entry_idx, 'Lat'] if has_gps else 0
        lon_val = lap.loc[entry_idx, 'Lon'] if has_gps else 0

        if has_gps and has_dist:
            print(f"  {pct:5.1f}% {dist_val:6.0f}m {lat_val:11.6f} {lon_val:12.6f} {entry_spd:6.0f}mph {min_spd:6.0f}mph")
        elif has_dist:
            print(f"  {pct:5.1f}% {dist_val:6.0f}m {entry_spd:6.0f}mph {min_spd:6.0f}mph")

    # Full lap trace at 10% intervals for track mapping reference
    if has_gps:
        print(f"\n  Full Lap GPS Trace (10% intervals):")
        print(f"  {'Pct':>5} {'Dist':>6} {'Lat':>11} {'Lon':>12} {'Speed':>7}")
        print(f"  {'-'*50}")
        for pct_target in range(0, 100, 10):
            section = lap[(lap['LapDistPct'] >= pct_target) & (lap['LapDistPct'] < pct_target + 1)]
            if not section.empty:
                row = section.iloc[0]
                spd = mps_to_mph(row['Speed'])
                dist_str = f"{row['LapDist']:5.0f}m" if has_dist else "    —"
                print(f"  {pct_target:4d}% {dist_str} {row['Lat']:11.6f} {row['Lon']:12.6f} {spd:6.0f}mph")


def corner_variance_analysis(df, valid_laps, best_lap):
    """Corner-by-corner time loss analysis across all valid laps."""
    print(f"\n{'='*65}")
    print("CORNER VARIANCE & TIME LOSS")
    print(f"{'='*65}")

    if len(valid_laps) < 3:
        print("  Need at least 3 valid laps for variance analysis.")
        return

    # Filter to laps with valid times only
    lap_times = {}
    for lap in valid_laps:
        t = df[df['Lap'] == lap]['LapLastLapTime'].iloc[-1]
        if t > 0:
            lap_times[lap] = t

    if len(lap_times) < 3:
        print("  Not enough laps with valid times.")
        return

    # Exclude incident laps (>10% slower than best)
    best_time = min(lap_times.values())
    clean_laps = [l for l, t in lap_times.items() if t < best_time * 1.10]

    if len(clean_laps) < 3:
        clean_laps = sorted(lap_times, key=lap_times.get)[:5]  # take 5 fastest

    # Define zones from braking points on best lap
    best_data = df[df['Lap'] == best_lap].copy().reset_index(drop=True)
    braking = best_data[best_data['Brake'] > 50][['LapDistPct']].copy()
    if braking.empty:
        print("  No braking zones found for sector definition.")
        return

    braking['zone'] = (braking['LapDistPct'].diff().abs() > 5).cumsum()
    zone_centers = braking.groupby('zone')['LapDistPct'].mean().values

    # Create sector boundaries from zone centers
    sectors = []
    for i, center in enumerate(zone_centers):
        start = center - 3
        end = center + 8  # extend past braking into corner exit
        sectors.append((start, end, center))

    # Calculate time in each sector for each clean lap
    sample_rate = 60
    sector_times = {i: [] for i in range(len(sectors))}

    for lap in clean_laps:
        lap_data = df[df['Lap'] == lap].copy().reset_index(drop=True)
        for i, (start, end, center) in enumerate(sectors):
            zone_data = lap_data[(lap_data['LapDistPct'] >= start) & (lap_data['LapDistPct'] <= end)]
            time_in_zone = len(zone_data) / sample_rate
            if time_in_zone > 0.5:  # minimum 0.5s to be valid
                sector_times[i].append(time_in_zone)

    # Calculate stats
    print(f"  Laps analyzed: {clean_laps} ({len(clean_laps)} laps)")
    print(f"\n  {'Zone':>6} {'Avg':>7} {'Best':>7} {'Loss':>7} {'StdDev':>7}  Priority")
    print(f"  {'-'*55}")

    results = []
    for i, (start, end, center) in enumerate(sectors):
        times = sector_times[i]
        if len(times) < 2:
            continue
        avg_t = np.mean(times)
        best_t = min(times)
        loss = avg_t - best_t
        std = np.std(times)
        results.append((center, avg_t, best_t, loss, std))

    # Sort by time loss (biggest first)
    results.sort(key=lambda x: x[3], reverse=True)

    for center, avg_t, best_t, loss, std in results:
        priority = ""
        if loss > 0.5:
            priority = "<-- HIGH PRIORITY"
        elif loss > 0.3:
            priority = "<-- medium"
        print(f"  {center:5.1f}% {avg_t:>6.2f}s {best_t:>6.2f}s {loss:>6.2f}s {std:>6.2f}s  {priority}")

    total_loss = sum(r[3] for r in results)
    print(f"\n  Total recoverable time: {total_loss:.2f}s (sum of all zone losses vs theoretical best)")

# ── Main ──────────────────────────────────────────────────────────────────────
def analyze(filepath):
    """
    Run full analysis and return structured results dict.
    This is the programmatic API — used by generate_session_notes.py.
    """
    if not os.path.exists(filepath):
        return None

    # Parse session metadata from .ibt header (car name, track name, event type)
    session_info = parse_session_info(filepath)

    df, sample_rate, vehicle, venue = parse_ibt(filepath)
    # Physics profile drives the coaching rules; the displayed class comes from
    # iRacing's own metadata so a GT3 is never labelled Touring.
    physics_profile = detect_car_class(vehicle, session_info.get('car_class_short'))
    car_class = physics_profile
    valid_laps = get_valid_laps(df)
    if not valid_laps:
        return None

    # Basic lap results
    lap_results = []
    for lap in valid_laps:
        ld = df[df['Lap'] == lap]
        time = ld['LapLastLapTime'].iloc[-1]
        abs_hits = int(ld['BrakeABSactive'].sum())
        max_spd = ld['Speed'].max()
        lap_results.append({
            'lap': lap, 'time': time, 'abs': abs_hits, 'max_speed_mph': max_spd,
        })

    valid_results = [r for r in lap_results if r['time'] > 0]
    if not valid_results:
        return None
    best_lap = min(valid_results, key=lambda x: x['time'])['lap']
    worst_lap = max(valid_results, key=lambda x: x['time'])['lap']

    # ABS trend
    mid = len(valid_laps) // 2
    early = valid_laps[:mid] if mid > 0 else valid_laps
    late = valid_laps[mid:] if mid > 0 else valid_laps
    early_avg = np.mean([int(df[df['Lap']==l]['BrakeABSactive'].sum()) for l in early])
    late_avg = np.mean([int(df[df['Lap']==l]['BrakeABSactive'].sum()) for l in late])

    # Track length first — every zone and window threshold is derived from a real
    # distance rather than a percentage of an unknown-length lap
    track_length = _track_length_from(df, best_lap)

    # Braking zones (best lap)
    braking_zones = _extract_braking_zones(df, best_lap, vehicle, sample_rate,
                                           track_length, physics_profile)

    # Trail braking (best lap)
    trail_braking = _extract_trail_braking(df, best_lap, track_length)

    # Corner variance (uses the rate derived from the file, not a fixed 60Hz)
    corner_variance = _extract_corner_variance(
        df, valid_laps, best_lap, sample_rate, track_length)

    # Tire temps
    tire_temps = _extract_tire_temps(df, best_lap)

    # GPS trace (dense, for all valid laps)
    gps_traces = {}  # lap_num -> trace array
    for lap_num in valid_laps:
        lap_trace = _extract_gps_trace(df, lap_num)
        if lap_trace:
            gps_traces[lap_num] = lap_trace

    # Best lap trace (for backward compat)
    gps_trace = gps_traces.get(best_lap, [])

    # Per-lap brake points (for consistency overlay)
    per_lap_brake_points = _extract_per_lap_brake_points(df, valid_laps, braking_zones)

    # Apex speed consistency + Min Speed Spread (per-zone, across laps)
    apex_consistency = _extract_apex_consistency(
        df, valid_laps, braking_zones, best_lap, track_length)

    # Exit metrics (Thr On, Thr Lag, Brake Linearity) for all valid laps
    exit_metrics_all = {}
    for lap_num in valid_laps:
        exit_metrics_all[lap_num] = _extract_exit_metrics(df, lap_num, braking_zones, sample_rate)
    # Best lap metrics (backward compat)
    exit_metrics = exit_metrics_all.get(best_lap, [])

    return {
        'filepath': filepath,
        'vehicle': vehicle,
        'venue': venue,
        'car_class': car_class,                 # physics profile (GT4 / Generic)
        'physics_profile': physics_profile,
        'car_class_display': display_car_class(session_info, physics_profile),
        'track_length_m': track_length,
        'sample_rate': sample_rate,
        'total_rows': len(df),
        'valid_laps': valid_laps,
        'best_lap': best_lap,
        'worst_lap': worst_lap,
        'lap_results': lap_results,
        'lap_abs_totals': [r['abs'] for r in lap_results if r['time'] > 0],
        'abs_trend': {
            'early_avg': early_avg, 'late_avg': late_avg,
            'delta': late_avg - early_avg,
            'early_laps': early, 'late_laps': late,
        },
        'braking_zones': braking_zones,
        'trail_braking': trail_braking,
        'corner_variance': corner_variance,
        'tire_temps': tire_temps,
        'gps_trace': gps_trace,
        'gps_traces': gps_traces,
        'per_lap_brake_points': per_lap_brake_points,
        'apex_consistency': apex_consistency,
        'exit_metrics': exit_metrics,
        'exit_metrics_all': {str(k): v for k, v in exit_metrics_all.items()},
        'session_info': session_info,
    }


def _extract_braking_zones(df, lap_num, vehicle, sample_rate=60, track_length_m=None,
                          car_class=None):
    """Extract braking zone data as list of dicts."""
    if car_class is None:
        car_class = detect_car_class(vehicle)
    lap = df[df['Lap'] == lap_num].copy().reset_index(drop=True)

    braking = lap[lap['Brake'] > 50][['LapDistPct','Speed','Brake','BrakeABSactive']].copy()
    if braking.empty:
        return []
    braking['zone'] = _zone_ids(braking['LapDistPct'], track_length_m)

    has_gear = 'Gear' in lap.columns and lap['Gear'].max() > 0
    has_gps = 'Lat' in lap.columns and 'Lon' in lap.columns
    has_dist = 'LapDist' in lap.columns

    zones = []
    for z, grp in braking.groupby('zone'):
        pos = grp['LapDistPct'].mean()
        entry_idx = grp.index[0]
        entry = grp['Speed'].iloc[0]
        min_spd = grp['Speed'].min()
        max_brk = grp['Brake'].max()
        abs_h = int(grp['BrakeABSactive'].sum())

        zone_data = {
            'pct': pos,
            'entry_pct': grp['LapDistPct'].iloc[0],
            'entry_mph': entry,
            'min_mph': min_spd,
            'max_brake': max_brk,
            'abs': abs_h,
            'dist_m': lap.loc[entry_idx, 'LapDist'] if has_dist else 0,
            'lat': lap.loc[entry_idx, 'Lat'] if has_gps else 0,
            'lon': lap.loc[entry_idx, 'Lon'] if has_gps else 0,
            't2peak': None,
            'brake_to_shift': None,
            'max_ds_rpm': 0,
            'apex_rpm': 0,
            'apex_brake': 0,
            'coast_time': None,
            'turnin_brake': None,
            'notes': [],
        }

        if not has_gear:
            zones.append(zone_data)
            continue

        # Extended zone for gear/apex analysis
        zone_start = grp['LapDistPct'].min() - 2
        zone_end = grp['LapDistPct'].max() + 5
        zone_full = lap[(lap['LapDistPct'] >= zone_start) & (lap['LapDistPct'] <= zone_end)].copy()

        # Brake-to-Shift Delta
        brake_start_idx = zone_full[zone_full['Brake'] > 10].index.min()
        gear_changes = zone_full[zone_full['Gear'].diff() < 0]
        if brake_start_idx is not None and not gear_changes.empty:
            first_ds_idx = gear_changes.index.min()
            zone_data['brake_to_shift'] = (first_ds_idx - brake_start_idx) / sample_rate

        # Max Downshift RPM
        if not gear_changes.empty:
            for ds_idx in gear_changes.index:
                window_end = ds_idx + int(0.5 * sample_rate)
                window = lap.loc[ds_idx:min(window_end, lap.index.max())]
                if 'RPM' in window.columns and not window.empty:
                    rpm_val = window['RPM'].max()
                    if rpm_val > zone_data['max_ds_rpm']:
                        zone_data['max_ds_rpm'] = rpm_val

        # Apex RPM + Apex Brake
        min_speed_idx = zone_full['Speed'].idxmin()
        zone_data['apex_rpm'] = zone_full.loc[min_speed_idx, 'RPM'] if 'RPM' in zone_full.columns else 0
        zone_data['apex_brake'] = zone_full.loc[min_speed_idx, 'Brake'] if 'Brake' in zone_full.columns else 0

        # Time to Peak Brake
        off_brake = zone_full[zone_full['Brake'] < 5]
        if not off_brake.empty:
            search_start = off_brake.index.min()
            after_release = zone_full.loc[search_start:]
            brake_initial_idx = after_release[after_release['Brake'] > 5].index.min()
        else:
            brake_initial_idx = zone_full[zone_full['Brake'] > 5].index.min()
        if brake_initial_idx is not None and not pd.isna(brake_initial_idx):
            zone_brake_data = zone_full.loc[brake_initial_idx:]
            if not zone_brake_data.empty:
                peak_idx = zone_brake_data['Brake'].idxmax()
                zone_data['t2peak'] = (peak_idx - brake_initial_idx) / sample_rate

        # Late-Zone ABS
        late_abs = False
        if abs_h > 2:
            zone_abs_data = grp[grp['BrakeABSactive'] > 0]
            if not zone_abs_data.empty:
                zone_midpoint = (grp['LapDistPct'].min() + grp['LapDistPct'].max()) / 2
                late_abs_hits = len(zone_abs_data[zone_abs_data['LapDistPct'] > zone_midpoint])
                early_abs_hits = len(zone_abs_data[zone_abs_data['LapDistPct'] <= zone_midpoint])
                late_abs = late_abs_hits > early_abs_hits

        # Coast Time (Stage 1: Transition) — time between throttle off and brake on
        coast_time = None
        # Look backwards from brake application to find when throttle dropped to 0
        if brake_initial_idx is not None and not pd.isna(brake_initial_idx):
            # Search before brake application for throttle lift
            pre_brake = lap.loc[max(0, brake_initial_idx - int(2.0 * sample_rate)):brake_initial_idx]
            if not pre_brake.empty and 'Throttle' in pre_brake.columns:
                # Find last sample where throttle was > 0 (pedal still pressed)
                throttle_on = pre_brake[pre_brake['Throttle'] > 0]
                if not throttle_on.empty:
                    throttle_off_idx = throttle_on.index.max()  # last sample with throttle
                    # Check for overlap (left-foot braking: brake > 1% while throttle > 0)
                    brake_at_throttle_off = lap.loc[throttle_off_idx, 'Brake'] if throttle_off_idx in lap.index else 0
                    if brake_at_throttle_off > 1:
                        coast_time = 0.0  # overlapping inputs
                    else:
                        # Coast time = gap between throttle off and brake on
                        coast_time = (brake_initial_idx - throttle_off_idx) / sample_rate
                        if coast_time < 0:
                            coast_time = 0.0
                else:
                    coast_time = 0.0  # throttle was already off
        zone_data['coast_time'] = coast_time

        # Turn-In Brake % (Stage 4: Rate of Release) — brake pressure at steering commitment
        turnin_brake = None
        # Find when steering angle first exceeds 15 degrees (0.2618 radians) in the braking zone
        if 'SteeringWheelAngle' in zone_full.columns:
            # Only look from brake application onwards
            steer_search = zone_full
            if brake_initial_idx is not None and not pd.isna(brake_initial_idx):
                steer_search = zone_full.loc[brake_initial_idx:]
            steering_commit = steer_search[steer_search['SteeringWheelAngle'].abs() > 0.2618]
            if not steering_commit.empty:
                turnin_idx = steering_commit.index.min()
                turnin_brake = lap.loc[turnin_idx, 'Brake'] if turnin_idx in lap.index else None
        zone_data['turnin_brake'] = turnin_brake

        # Diagnostic flags
        notes = []
        if abs_h > 0:
            notes.append("[ABS]")
        if car_class == "GT4":
            if zone_data['t2peak'] is not None and zone_data['t2peak'] > 0.4:
                notes.append("Lazy Initial Brake")
            if late_abs:
                notes.append("Late Brake Squeeze")
            if zone_data['apex_brake'] > 15 and min_spd > OVER_SLOWING_MIN_SPEED_MPS:
                notes.append("Over-slowing (Trust GT4 Grip)")
            if zone_data['brake_to_shift'] is not None and zone_data['brake_to_shift'] >= 0 and zone_data['brake_to_shift'] < 0.15:
                notes.append("Early Shift (Protection Risk)")
            if zone_data['max_ds_rpm'] > 7500:
                notes.append("Over-rev Risk")
            if zone_data['apex_rpm'] < 4000 and min_spd > LUGGING_MIN_SPEED_MPS:
                notes.append("Lugging")
        else:
            if zone_data['brake_to_shift'] is not None and zone_data['brake_to_shift'] >= 0 and zone_data['brake_to_shift'] < 0.2:
                notes.append("Early Shift")
            if zone_data['max_ds_rpm'] > 7000:
                notes.append("Aggressive Shift")
            if zone_data['apex_rpm'] < 3500 and min_spd > LUGGING_MIN_SPEED_MPS:
                notes.append("Lugging")

        # Input Stability: detect brake pumping during mid-corner phase
        # Count sign changes in diff(Brake) between turn-in and apex
        if brake_initial_idx is not None and not pd.isna(brake_initial_idx):
            mid_corner = zone_full.loc[brake_initial_idx:min_speed_idx]
            if len(mid_corner) > 5 and 'Brake' in mid_corner.columns:
                brake_diff = mid_corner['Brake'].diff().dropna()
                sign_changes = ((brake_diff[:-1].values * brake_diff[1:].values) < 0).sum()
                if sign_changes >= 3:
                    notes.append("[Oscillating]")

        zone_data['notes'] = notes
        zones.append(zone_data)

    return zones


def _extract_trail_braking(df, lap_num, track_length_m=None):
    """Extract trail braking data as list of dicts."""
    lap = df[df['Lap'] == lap_num].copy()
    trail = lap[
        (lap['Brake'] > 10) & (lap['SteeringWheelAngle'].abs() > 0.1)
    ][['LapDistPct','Brake','LatAccel','YawRate']].copy()
    if trail.empty:
        return []

    trail['zone'] = _zone_ids(trail['LapDistPct'], track_length_m)
    results = []
    for z, grp in trail.groupby('zone'):
        pos = grp['LapDistPct'].mean()
        brk = grp['Brake'].mean()
        lat = grp['LatAccel'].abs().max()
        yaw = grp['YawRate'].abs().max()
        diag = diagnose_trail_zone(brk, lat, yaw)
        results.append({'pct': pos, 'brake': brk, 'lat_g': lat, 'yaw': yaw, 'diagnosis': diag})
    return results


def _corner_sectors(zone_centers, lead_pct=3.0, trail_pct=8.0):
    """Build non-overlapping (start, end, center) sectors around corner centres.

    The raw centre-3%/+8% windows overlap whenever corners are close together,
    which double-counts time when per-corner losses are summed. Boundaries are
    clamped to the midpoint between adjacent centres so each piece of track is
    attributed to exactly one corner.
    """
    sectors = []
    for i, center in enumerate(zone_centers):
        center = float(center)
        start, end = center - lead_pct, center + trail_pct
        if i > 0:
            start = max(start, (float(zone_centers[i - 1]) + center) / 2.0)
        if i < len(zone_centers) - 1:
            end = min(end, (center + float(zone_centers[i + 1])) / 2.0)
        if end > start:
            sectors.append((start, end, center))
    return sectors


def _extract_corner_variance(df, valid_laps, best_lap, sample_rate=60, track_length_m=None):
    """Extract corner variance data as list of dicts.

    Time in each sector is sample_count / sample_rate. Validated against
    interpolating the lap-time channel: agreement within ~0.01s at 60Hz.
    The sample rate must be the rate actually derived from the file — a
    hardcoded value silently rescales every reported loss.
    """
    if len(valid_laps) < 3:
        return []

    lap_times = {}
    for lap in valid_laps:
        t = df[df['Lap'] == lap]['LapLastLapTime'].iloc[-1]
        if t > 0:
            lap_times[lap] = t
    if len(lap_times) < 3:
        return []

    best_time = min(lap_times.values())
    clean_laps = [l for l, t in lap_times.items() if t < best_time * 1.10]
    if len(clean_laps) < 3:
        clean_laps = sorted(lap_times, key=lap_times.get)[:5]

    best_data = df[df['Lap'] == best_lap].copy().reset_index(drop=True)
    braking = best_data[best_data['Brake'] > 50][['LapDistPct']].copy()
    if braking.empty:
        return []

    braking['zone'] = _zone_ids(braking['LapDistPct'], track_length_m)
    zone_centers = braking.groupby('zone')['LapDistPct'].mean().values

    sectors = _corner_sectors(zone_centers)
    if not sectors:
        return []
    sector_times = {i: [] for i in range(len(sectors))}

    for lap in clean_laps:
        lap_data = df[df['Lap'] == lap].copy().reset_index(drop=True)
        for i, (start, end, center) in enumerate(sectors):
            zone_data = lap_data[(lap_data['LapDistPct'] >= start) & (lap_data['LapDistPct'] <= end)]
            time_in_zone = len(zone_data) / sample_rate
            if time_in_zone > 0.5:
                sector_times[i].append(time_in_zone)

    results = []
    for i, (start, end, center) in enumerate(sectors):
        times = sector_times[i]
        if len(times) < 2:
            continue
        avg_t = np.mean(times)
        best_t = min(times)
        loss = avg_t - best_t
        std = np.std(times)
        results.append({'pct': center, 'avg': avg_t, 'best': best_t, 'loss': loss, 'std': std})

    results.sort(key=lambda x: x['loss'], reverse=True)
    return results


def _extract_tire_temps(df, lap_num):
    """Extract tire temps (under-load only) as dict."""
    lap = df[df['Lap'] == lap_num]
    under_load = lap[
        (lap['LatAccel'].abs() >= LOAD_LAT_G) | (lap['LongAccel'].abs() >= LOAD_LONG_G)
    ]
    if len(under_load) < 50:
        return {}

    temps = {}
    for corner, (ic, mc, oc) in [('LF',('LFtempL','LFtempM','LFtempR')),
                                   ('RF',('RFtempL','RFtempM','RFtempR')),
                                   ('LR',('LRtempL','LRtempM','LRtempR')),
                                   ('RR',('RRtempL','RRtempM','RRtempR'))]:
        if not all(c in under_load.columns for c in [ic, mc, oc]):
            continue
        i, m, o = under_load[ic].mean(), under_load[mc].mean(), under_load[oc].mean()
        # Stored in °C; the display layer converts.
        temps[corner] = {
            'inner': i, 'mid': m, 'outer': o,
            'avg': (i + m + o) / 3
        }
    return temps


def _extract_exit_metrics(df, lap_num, braking_zones, sample_rate=60):
    """Extract corner exit metrics and brake release curve for each braking zone.

    For each zone, calculates:
    - thr_on: time from apex (min speed) to first 100% throttle (seconds)
    - thr_lag: time spent between 20-80% throttle before exceeding 80% (seconds)
    - brake_linearity: R² score of linear fit to brake release phase (0–1)
    - brake_release_curve: normalized array of brake % values from peak to zero (for visualization)

    Returns list of dicts parallel to braking_zones.
    """
    if not braking_zones:
        return []

    lap = df[df['Lap'] == lap_num].copy().reset_index(drop=True)
    if lap.empty or 'Throttle' not in lap.columns:
        return [{'thr_on': None, 'thr_lag': None, 'brake_linearity': None, 'brake_release_curve': [], 'brake_duration_s': None} for _ in braking_zones]

    results = []
    for zone in braking_zones:
        zone_center = zone['pct']
        # Define the exit search window: from zone center to +15% of track
        exit_start = zone_center - 2
        exit_end = zone_center + 15

        zone_data = lap[(lap['LapDistPct'] >= exit_start) & (lap['LapDistPct'] <= exit_end)]
        if zone_data.empty:
            results.append({'thr_on': None, 'thr_lag': None, 'brake_linearity': None, 'brake_release_curve': [], 'brake_duration_s': None})
            continue

        # Find apex (minimum speed point in this zone)
        apex_idx = zone_data['Speed'].idxmin()
        apex_speed = zone_data.loc[apex_idx, 'Speed']  # m/s

        # === Brake Release Curve & Linearity ===
        # Find peak brake in this zone, then extract the release phase (peak → 0%)
        brake_in_zone = zone_data['Brake']
        peak_brake_idx = brake_in_zone.idxmax()
        peak_brake_val = brake_in_zone.loc[peak_brake_idx]

        # Release phase: from peak brake to where brake drops below 2%
        release_phase = lap.loc[peak_brake_idx:]
        brake_zero = release_phase[release_phase['Brake'] < 2]
        if not brake_zero.empty and peak_brake_val > 20:
            end_release_idx = brake_zero.index.min()
            release_data = lap.loc[peak_brake_idx:end_release_idx, 'Brake'].values

            # Normalize to 0–1 for the curve (peak = 1.0, zero = 0.0)
            if len(release_data) > 3:
                curve_normalized = (release_data / peak_brake_val).tolist()
                # Downsample to max 20 points for compact JSON
                if len(curve_normalized) > 20:
                    step = len(curve_normalized) / 20
                    curve_normalized = [curve_normalized[int(i * step)] for i in range(20)]

                # Linearity score: R² of linear fit
                import numpy as np
                n = len(release_data)
                x = np.arange(n)
                # Perfect linear release: y goes from max to 0 linearly
                # Fit actual data with linear regression
                if n > 2:
                    coeffs = np.polyfit(x, release_data, 1)
                    predicted = np.polyval(coeffs, x)
                    ss_res = np.sum((release_data - predicted) ** 2)
                    ss_tot = np.sum((release_data - np.mean(release_data)) ** 2)
                    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
                    brake_linearity = round(max(0, min(1, r_squared)), 2)
                else:
                    brake_linearity = None
            else:
                curve_normalized = []
                brake_linearity = None
        else:
            curve_normalized = []
            brake_linearity = None

        # Brake duration: time from peak brake to release (end of braking event)
        if not brake_zero.empty and peak_brake_val > 20:
            brake_duration = round((end_release_idx - peak_brake_idx) / sample_rate, 2)
        else:
            brake_duration = None

        # === Throttle Exit Metrics ===
        # Skip very slow hairpins where 100% throttle is trivial
        if apex_speed < EXIT_METRICS_MIN_APEX_MPS:
            results.append({'thr_on': None, 'thr_lag': None, 'brake_linearity': brake_linearity, 'brake_release_curve': curve_normalized, 'brake_duration_s': brake_duration})
            continue

        # Scan forward from apex
        post_apex = lap.loc[apex_idx:]

        # thr_on: time from apex to first sample where Throttle >= 99%
        full_throttle = post_apex[post_apex['Throttle'] >= 99]
        if not full_throttle.empty:
            wot_idx = full_throttle.index.min()
            thr_on = (wot_idx - apex_idx) / sample_rate
            if thr_on > 10:
                thr_on = None
        else:
            thr_on = None

        # thr_lag: time spent in 20-80% band before exceeding 80%
        above_80 = post_apex[post_apex['Throttle'] > 80]
        if not above_80.empty:
            exit_80_idx = above_80.index.min()
            mid_band = post_apex.loc[apex_idx:exit_80_idx]
            feathering = mid_band[(mid_band['Throttle'] >= 20) & (mid_band['Throttle'] <= 80)]
            thr_lag = len(feathering) / sample_rate
        else:
            thr_lag = None

        results.append({
            'thr_on': round(thr_on, 2) if thr_on is not None else None,
            'thr_lag': round(thr_lag, 2) if thr_lag is not None else None,
            'brake_linearity': brake_linearity,
            'brake_release_curve': curve_normalized,
            'brake_duration_s': brake_duration,
        })

    return results


# Gap between braking samples that marks a new braking zone. Expressed in metres
# because a fixed percentage does not scale: the original 5% is 270m on a 5.4km
# lap, which merges genuinely separate corners into one zone and then reports a
# neighbouring corner's apex speed.
ZONE_GAP_METERS = 120.0
DEFAULT_ZONE_GAP_PCT = 5.0
ZONE_GAP_MIN_PCT = 1.0
ZONE_GAP_MAX_PCT = 10.0


def _zone_gap_pct(track_length_m=None):
    """Distance-based zone split threshold, as a percentage of the lap."""
    if track_length_m and track_length_m > 0:
        gap = (ZONE_GAP_METERS / float(track_length_m)) * 100.0
        return min(max(gap, ZONE_GAP_MIN_PCT), ZONE_GAP_MAX_PCT)
    return DEFAULT_ZONE_GAP_PCT


def _zone_ids(pct_series, track_length_m=None):
    """Group consecutive samples into zones, splitting on a real distance gap."""
    return (pct_series.diff().abs() > _zone_gap_pct(track_length_m)).cumsum()


def _track_length_from(df, lap_num):
    """Lap length in metres from the LapDist channel, or 0 if unavailable."""
    if 'LapDist' not in df.columns:
        return 0.0
    lap_data = df[df['Lap'] == lap_num]
    if lap_data.empty:
        return 0.0
    return float(lap_data['LapDist'].max())


def _clean_lap_numbers(df, valid_laps, slower_factor=1.10, min_laps=3, fallback_n=5):
    """Return laps excluding incidents (>10% slower than best).

    Mirrors the lap selection already used by corner variance so speed-based
    coaching metrics are computed over the same laps as the time-loss figures
    they are presented alongside. A single spin or off-track lap would otherwise
    dominate a min-speed range.

    Falls back to all valid laps when lap times are unavailable.
    """
    if 'LapLastLapTime' not in df.columns:
        return list(valid_laps)

    lap_times = {}
    for lap in valid_laps:
        lap_data = df[df['Lap'] == lap]
        if lap_data.empty:
            continue
        lap_time = float(lap_data['LapLastLapTime'].iloc[-1])
        if lap_time > 0:
            lap_times[lap] = lap_time

    if not lap_times:
        return list(valid_laps)

    best_time = min(lap_times.values())
    clean = [lap for lap, t in lap_times.items() if t < best_time * slower_factor]
    if len(clean) < min_laps:
        clean = sorted(lap_times, key=lap_times.get)[:fallback_n]
    return clean


# Minimum clean laps before outlier rejection is applied to the min-speed band.
# Below this there is not enough data to distinguish an outlier from real spread.
MIN_LAPS_FOR_OUTLIER_REJECTION = 5

# Tukey fence multiplier for rejecting min-speed outliers (standard 1.5 x IQR)
OUTLIER_IQR_MULTIPLIER = 1.5

# Apex search window, expressed in metres either side of the corner's APEX.
# A percentage-only window is not corner-specific: on a 5.4km circuit the old
# +/-5%/+8% window spanned ~700m, so "minimum speed at this corner" could pick up
# a slow moment hundreds of metres away and report it as over-braking.
#
# The window must be centred on the apex, not on the braking zone. Measured on a
# real 5.4km lap the apex sits 55-273m (mean 119m) AFTER the braking-zone centre,
# so a braking-centred window catches the car still at entry speed on some laps
# and at the apex on others, manufacturing variance that is not driver error.
APEX_WINDOW_METERS = 100.0
# Region searched on the best lap to locate each corner's apex
APEX_LOCATE_BACK_METERS = 60.0
APEX_LOCATE_FORWARD_METERS = 300.0
DEFAULT_APEX_LOCATE_BACK_PCT = 1.5
DEFAULT_APEX_LOCATE_FORWARD_PCT = 8.0


def _apex_reference_pcts(df, best_lap, zone_centers, track_length_m=None):
    """Locate each corner's apex (minimum-speed point) on the best lap.

    The best lap is used as a single stable reference for all laps so the search
    window is identical lap to lap; per-lap apex drift then shows up as real
    variation rather than as a moving goalpost.
    """
    def to_pct(meters, fallback):
        if track_length_m and track_length_m > 0:
            return (meters / float(track_length_m)) * 100.0
        return fallback

    back = to_pct(APEX_LOCATE_BACK_METERS, DEFAULT_APEX_LOCATE_BACK_PCT)
    forward = to_pct(APEX_LOCATE_FORWARD_METERS, DEFAULT_APEX_LOCATE_FORWARD_PCT)

    best_data = df[df['Lap'] == best_lap]
    apex_pcts = []
    for i, center in enumerate(zone_centers):
        center = float(center)
        low, high = center - back, center + forward
        # Never search past the next corner's braking point
        if i < len(zone_centers) - 1:
            high = min(high, float(zone_centers[i + 1]))
        seg = best_data[(best_data['LapDistPct'] >= low) & (best_data['LapDistPct'] <= high)]
        if seg.empty or 'Speed' not in seg.columns:
            apex_pcts.append(center)
        else:
            apex_pcts.append(float(seg.loc[seg['Speed'].idxmin(), 'LapDistPct']))
    return apex_pcts
# Guard rails when converting to % of lap (very short or very long tracks)
APEX_MIN_HALF_WIDTH_PCT = 1.0
APEX_MAX_HALF_WIDTH_PCT = 4.0
# Used only when track length is unavailable
DEFAULT_APEX_HALF_WIDTH_PCT = 2.5
# Never let neighbour clamping shrink a window below this
APEX_MIN_WINDOW_PCT = 0.6


def _apex_window(apex_pcts, idx, track_length_m=None):
    """Return (low_pct, high_pct) search window for a corner's minimum speed.

    The window is a fixed physical distance either side of the corner's apex
    position, then clamped to the midpoints with the neighbouring corners so two
    corners can never draw their apex speed from the same piece of track.
    """
    center = float(apex_pcts[idx])

    if track_length_m and track_length_m > 0:
        half = (APEX_WINDOW_METERS / float(track_length_m)) * 100.0
        half = min(max(half, APEX_MIN_HALF_WIDTH_PCT), APEX_MAX_HALF_WIDTH_PCT)
    else:
        half = DEFAULT_APEX_HALF_WIDTH_PCT

    low, high = center - half, center + half

    # Clamp to midpoints with adjacent corners
    if idx > 0:
        low = max(low, (float(apex_pcts[idx - 1]) + center) / 2.0)
    if idx < len(apex_pcts) - 1:
        high = min(high, (center + float(apex_pcts[idx + 1])) / 2.0)

    # Duplicate/near-duplicate zones can clamp the window to nothing — fall back
    # to the physical window rather than returning no data.
    if high - low < APEX_MIN_WINDOW_PCT:
        low, high = center - half, center + half

    return low, high


def _outlier_trimmed_band(values):
    """Return (low, high) for values with Tukey-fence outliers removed.

    Uses the standard 1.5 x IQR rule. A single off-track moment sits outside the
    fence and is dropped, so the band describes laps the driver actually repeats.
    Falls back to the raw range when there is too little data or when trimming
    would remove everything.
    """
    if len(values) < MIN_LAPS_FOR_OUTLIER_REJECTION:
        return float(min(values)), float(max(values))

    q1 = float(np.percentile(values, 25))
    q3 = float(np.percentile(values, 75))
    iqr = q3 - q1
    low_fence = q1 - OUTLIER_IQR_MULTIPLIER * iqr
    high_fence = q3 + OUTLIER_IQR_MULTIPLIER * iqr

    kept = [float(v) for v in values if low_fence <= v <= high_fence]
    if not kept:
        return float(min(values)), float(max(values))
    return min(kept), max(kept)


# Coaching trigger levels, expressed as a fraction of the corner's apex speed
# with an absolute floor. A fixed threshold is far more sensitive on fast
# corners than slow ones: 10mph is 25% of a 40mph hairpin but 11% of a 90mph
# sweeper, which is why 5 of 8 corners fired on a real 5.4km lap.
#
# The fractions are unit-agnostic. The floors are SI (m/s); their historical
# mph values are shown so the tuning history in RR-021/RR-022 stays traceable.
SPREAD_LIMIT_FRACTION = 0.20
SPREAD_LIMIT_FLOOR_MPS = mph_to_mps(6.0)            # 6.0 mph
OVER_BRAKING_LIMIT_FRACTION = 0.07
OVER_BRAKING_LIMIT_FLOOR_MPS = mph_to_mps(1.5)      # 1.5 mph
APEX_STD_LIMIT_FRACTION = 0.08
APEX_STD_LIMIT_FLOOR_MPS = mph_to_mps(2.0)          # 2.0 mph


def _empty_apex_result():
    """Return an apex/min-speed result dict with all metrics unavailable."""
    return {
        'avg_apex_mph': None,
        'std_apex_mph': None,
        'spread_limit_mph': None,
        'over_braking_limit_mph': None,
        'apex_std_limit_mph': None,
        'per_lap_apex': [],
        'min_speed_best_mph': None,
        'min_speed_worst_mph': None,
        'min_speed_typical_low_mph': None,
        'min_speed_typical_high_mph': None,
        'min_speed_spread_mph': None,
        'over_braking_mph': None,
    }


def _extract_apex_consistency(df, valid_laps, braking_zones, best_lap=None,
                              track_length_m=None):
    """Compute apex speed consistency and Min Speed Spread per braking zone.

    For each zone, collects the minimum speed from every valid lap and computes:
    - avg_apex_mph: mean min speed across laps
    - std_apex_mph: standard deviation (lower = more consistent)
    - per_lap_apex: list of {lap, apex_speed_mph} for each lap
    - min_speed_best_mph: min speed recorded on the best lap in this zone
    - min_speed_worst_mph: true slowest min speed across clean laps
    - min_speed_typical_low_mph / min_speed_typical_high_mph: representative band
      with Tukey-fence outliers removed once there are enough clean laps
    - min_speed_spread_mph: width of that representative band
    - over_braking_mph: best-lap min speed minus average min speed

    The band trims outliers for larger samples because a raw max-minus-min range
    is dominated by a single off-track moment, which would report a large spread
    for an otherwise repeatable corner.

    Sign convention: `over_braking_mph` is POSITIVE when the average lap carries
    less speed than the best lap — i.e. the driver is over-slowing by that many
    mph on a typical lap. Negative means the best lap was the slowest through
    the corner, so over-braking is not indicated.

    Aggregates (avg/std/spread/over-braking) are computed over clean laps only,
    excluding incident laps, so a single spin cannot masquerade as over-braking.
    `per_lap_apex` still reports every valid lap for transparency.

    Args:
        df: normalized telemetry DataFrame
        valid_laps: list of valid lap numbers
        braking_zones: braking zones from the best lap
        best_lap: best lap number, used for the over-braking reference

    Returns list of dicts parallel to braking_zones.
    """
    if not braking_zones or len(valid_laps) < 2:
        return [_empty_apex_result() for _ in braking_zones]

    clean_laps = set(_clean_lap_numbers(df, valid_laps))
    zone_centers = [z['pct'] for z in braking_zones]
    # Centre each search window on the corner's apex, not its braking point
    apex_pcts = _apex_reference_pcts(df, best_lap, zone_centers, track_length_m)

    results = []
    for zone_idx, zone in enumerate(braking_zones):
        search_min, search_max = _apex_window(apex_pcts, zone_idx, track_length_m)

        apex_speeds = []
        per_lap = []
        best_lap_min = None
        for lap_num in valid_laps:
            lap_data = df[df['Lap'] == lap_num]
            if lap_data.empty:
                continue
            zone_data = lap_data[
                (lap_data['LapDistPct'] >= search_min) &
                (lap_data['LapDistPct'] <= search_max)
            ]
            if zone_data.empty:
                continue
            min_speed = float(zone_data['Speed'].min())
            per_lap.append({'lap': int(lap_num), 'apex_speed_mph': min_speed})
            if lap_num in clean_laps:
                apex_speeds.append(min_speed)
            if best_lap is not None and lap_num == best_lap:
                best_lap_min = min_speed

        if len(apex_speeds) >= 2:
            slowest_min = float(min(apex_speeds))

            # Representative band — rejects single-lap outliers (spins/offs)
            band_low, band_high = _outlier_trimmed_band(apex_speeds)

            # Average/std MUST use the same trimmed set as the band. Otherwise a
            # value already rejected as an outlier still drags the mean and
            # inflates the reported over-slowing figure.
            trimmed = [v for v in apex_speeds if band_low <= v <= band_high] or apex_speeds
            avg = float(np.mean(trimmed))
            std = float(np.std(trimmed))

            # Speed-relative trigger levels. A flat 10mph spread is 25% of a
            # 40mph hairpin but only 11% of a 90mph sweeper, so a fixed figure
            # fires constantly on fast corners where that variation is normal.
            # reference_speed is m/s; the fractions are unit-agnostic and the
            # floors are SI, so the trigger levels are unchanged in real terms.
            reference_speed = max(avg, mph_to_mps(1.0))
            spread_limit = max(SPREAD_LIMIT_FRACTION * reference_speed,
                              SPREAD_LIMIT_FLOOR_MPS)
            over_braking_limit = max(OVER_BRAKING_LIMIT_FRACTION * reference_speed,
                                    OVER_BRAKING_LIMIT_FLOOR_MPS)
            apex_std_limit = max(APEX_STD_LIMIT_FRACTION * reference_speed,
                                APEX_STD_LIMIT_FLOOR_MPS)

            # Stored unrounded in m/s. Both consumers round at their own display
            # boundary (report and notes to 1dp mph, summary.py to 1dp mph), so
            # rounding here would only discard precision — and rounding a limit
            # can push it below the constant it was derived from.
            # float() rather than round() keeps NumPy scalars out of the contract
            # (RR-002) now that rounding no longer does that incidentally.
            result = {
                'avg_apex_mph': float(avg),
                'std_apex_mph': float(std),
                'spread_limit_mph': float(spread_limit),
                'over_braking_limit_mph': float(over_braking_limit),
                'apex_std_limit_mph': float(apex_std_limit),
                'per_lap_apex': per_lap,
                'min_speed_best_mph': float(best_lap_min) if best_lap_min is not None else None,
                'min_speed_worst_mph': float(slowest_min),
                'min_speed_typical_low_mph': float(band_low),
                'min_speed_typical_high_mph': float(band_high),
                'min_speed_spread_mph': float(band_high - band_low),
                'over_braking_mph': float(best_lap_min - avg) if best_lap_min is not None else None,
            }
            results.append(result)
        else:
            result = _empty_apex_result()
            result['per_lap_apex'] = per_lap
            results.append(result)

    return results


def _extract_per_lap_brake_points(df, valid_laps, braking_zones):
    """Extract the GPS coordinates where braking begins on each lap for each zone.

    For each braking zone (from best-lap analysis), finds where Brake first
    crosses 15% on every valid lap. Returns per-zone clusters for consistency
    visualization on the track map.
    """
    has_gps = 'Lat' in df.columns and 'Lon' in df.columns
    has_dist = 'LapDist' in df.columns
    if not has_gps or not braking_zones:
        return []

    # Get track length for spread-in-meters calculation
    track_length_m = 0
    if has_dist:
        sample_lap = df[df['Lap'] == valid_laps[0]]
        if not sample_lap.empty:
            track_length_m = sample_lap['LapDist'].max()

    results = []
    for zone in braking_zones:
        zone_center = zone['pct']
        # Define a search window around the known braking zone (±8% of track)
        search_min = zone_center - 8
        search_max = zone_center + 3  # braking starts before zone center

        entries = []
        for lap_num in valid_laps:
            lap_data = df[df['Lap'] == lap_num].copy()
            if lap_data.empty:
                continue

            # Find samples in the zone's approach region
            approach = lap_data[
                (lap_data['LapDistPct'] >= search_min) &
                (lap_data['LapDistPct'] <= search_max)
            ]
            if approach.empty:
                continue

            # Find first sample where Brake > 15% (braking point)
            braking_start = approach[approach['Brake'] > 15]
            if braking_start.empty:
                continue

            first_brake = braking_start.iloc[0]
            entries.append({
                'lap': int(lap_num),
                'entry_pct': float(first_brake['LapDistPct']),
                'lat': float(first_brake['Lat']),
                'lon': float(first_brake['Lon']),
                'speed_mph': float(first_brake['Speed']),
            })

        if not entries:
            continue

        # Calculate spread (consistency metric)
        entry_pcts = [e['entry_pct'] for e in entries]
        spread_pct = float(np.std(entry_pcts)) if len(entry_pcts) > 1 else 0.0
        spread_meters = spread_pct * track_length_m / 100.0 if track_length_m > 0 else 0.0

        results.append({
            'zone_pct': zone_center,
            'turn_name': '',  # filled in by report.py with track_map lookup
            'entries': entries,
            'spread_pct': round(spread_pct, 2),
            'spread_meters': round(spread_meters, 1),
        })

    return results


def _extract_gps_trace(df, lap_num, dense=True):
    """Extract GPS trace for track mapping.

    If dense=True (default), returns ~200 points (every 0.5% of lap distance)
    with full telemetry channels for heatmap visualization.
    If dense=False, returns the legacy 10-point trace.
    """
    has_gps = 'Lat' in df.columns and 'Lon' in df.columns
    has_dist = 'LapDist' in df.columns
    if not has_gps:
        return []

    lap = df[df['Lap'] == lap_num].copy().reset_index(drop=True)
    step = 0.5 if dense else 10
    trace = []

    pct_target = 0.0
    while pct_target < 100.0:
        section = lap[(lap['LapDistPct'] >= pct_target) & (lap['LapDistPct'] < pct_target + step)]
        if not section.empty:
            row = section.iloc[0]
            point = {
                'pct': round(pct_target, 1),
                'lat': row['Lat'],
                'lon': row['Lon'],
                'speed_mph': row['Speed'],
            }
            if has_dist:
                point['dist'] = row['LapDist']
            if dense:
                point['brake'] = row['Brake'] if 'Brake' in lap.columns else 0
                point['throttle'] = row['Throttle'] if 'Throttle' in lap.columns else 0
                point['gear'] = int(row['Gear']) if 'Gear' in lap.columns else 0
                point['steering'] = float(row['SteeringWheelAngle'] * 180 / 3.14159) if 'SteeringWheelAngle' in lap.columns else 0
            trace.append(point)
        pct_target += step

    return trace


def main():
    # Find the .ibt file
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        # Find largest .ibt in telemetry root
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ibts = glob.glob(os.path.join(root, "*.ibt"))
        if not ibts:
            print("No .ibt files found.")
            return
        filepath = max(ibts, key=os.path.getsize)
        print(f"Auto-selected: {os.path.basename(filepath)} ({os.path.getsize(filepath)/1024/1024:.1f} MB)")

    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    # Parse
    print(f"\nParsing: {os.path.basename(filepath)}")
    df, sample_rate, vehicle, venue = parse_ibt(filepath)
    print(f"  Car: {vehicle}  Track: {venue}  Rate: {sample_rate}Hz  Rows: {len(df):,}")

    # Get valid laps
    valid_laps = get_valid_laps(df)
    if not valid_laps:
        print("  No valid complete laps found.")
        return
    print(f"  Valid laps: {valid_laps}")

    # Run analysis
    best_lap, worst_lap = lap_summary(df, valid_laps)
    abs_trend(df, valid_laps)
    braking_analysis(df, best_lap, vehicle)
    track_position_map(df, best_lap)
    tire_temp_analysis(df, best_lap)
    trail_braking_analysis(df, best_lap)
    corner_variance_analysis(df, valid_laps, best_lap)

    # Low RPM
    best_data = df[df['Lap'] == best_lap]
    low_rpm = best_data[(best_data['RPM'] < 3000) & (best_data['Speed'] > 5)]
    if not low_rpm.empty:
        print(f"\n{'='*65}")
        print(f"LOW RPM — Lap {best_lap}")
        print(f"{'='*65}")
        low_rpm_z = low_rpm.copy()
        low_rpm_z['zone'] = (low_rpm_z['LapDistPct'].diff().abs() > 5).cumsum()
        for z, grp in low_rpm_z.groupby('zone'):
            print(f"  Track {grp['LapDistPct'].mean():.1f}%: "
                  f"{grp['RPM'].mean():.0f} RPM at {grp['Speed'].mean()*3.6:.0f}mph")

    print(f"\n{'='*65}")
    print("DONE")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
