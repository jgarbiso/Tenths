"""
Synthetic .ibt generator for tests.

Writes a byte-valid iRacing telemetry file that pyirsdk can open, so the whole
parse -> analyse -> report pipeline can be exercised on any machine, including CI,
with no dependence on the developer's archive.

More importantly it gives **known ground truth**. Real .ibt files can only be
asserted against loose ranges; here the apex speed of every corner on every lap
is dialled in, so the analyser's output can be checked exactly.

Binary layout (from pyirsdk's Header / DiskSubHeader / VarHeader):

    0    Header           version, status, tick_rate, session_info_update,
                          session_info_len, session_info_offset, num_vars,
                          var_header_offset, num_buf, buf_len
    48   VarBuffer[0]     tick_count, buf_offset            (16-byte stride)
    112  DiskSubHeader    start_date(Q), start_time(d), end_time(d),
                          lap_count(i), session_record_count(i)
    144  VarHeader[n]     type(i), offset(i), count(i), count_as_time(?),
                          name(32s), desc(64s), unit(32s)      (144 bytes each)
    ...  session info     YAML text, session_info_len bytes
    ...  sample data      session_record_count rows of buf_len bytes

Values are written in native iRacing units, because the analyser is what applies
normalisation: Throttle/Brake and LapDistPct are fractions 0..1, speed is m/s,
temperatures are Celsius.
"""

import struct

import yaml

VAR_HEADER_SIZE = 144
VAR_HEADER_OFFSET = 144
DISK_SUB_HEADER_OFFSET = 112

# pyirsdk's VAR_TYPE_MAP index -> struct code
TYPE_CHAR = 2   # int
TYPE_BOOL = 1
TYPE_INT = 2
TYPE_FLOAT = 4
TYPE_DOUBLE = 5

_FMT = {TYPE_BOOL: '?', TYPE_INT: 'i', TYPE_FLOAT: 'f', TYPE_DOUBLE: 'd'}
_SIZE = {TYPE_BOOL: 1, TYPE_INT: 4, TYPE_FLOAT: 4, TYPE_DOUBLE: 8}

# Channels written. Covers everything tenths.analyzer.COACHING_CHANNELS uses,
# plus SessionTime (sample-rate derivation).
CHANNELS = [
    ("SessionTime", TYPE_DOUBLE, "s"),
    ("SessionTick", TYPE_INT, ""),
    ("Lap", TYPE_INT, ""),
    ("LapCompleted", TYPE_INT, ""),
    ("LapDist", TYPE_FLOAT, "m"),
    ("LapDistPct", TYPE_FLOAT, "%"),
    ("LapCurrentLapTime", TYPE_FLOAT, "s"),
    ("LapLastLapTime", TYPE_FLOAT, "s"),
    ("LapBestLapTime", TYPE_FLOAT, "s"),
    ("LapDeltaToBestLap", TYPE_FLOAT, "s"),
    ("LapDeltaToOptimalLap", TYPE_FLOAT, "s"),
    ("Speed", TYPE_FLOAT, "m/s"),
    ("RPM", TYPE_FLOAT, "revs/min"),
    ("Gear", TYPE_INT, ""),
    ("Throttle", TYPE_FLOAT, "%"),
    ("Brake", TYPE_FLOAT, "%"),
    ("SteeringWheelAngle", TYPE_FLOAT, "rad"),
    ("BrakeABSactive", TYPE_BOOL, ""),
    ("BrakeABScutPct", TYPE_FLOAT, "%"),
    ("LongAccel", TYPE_FLOAT, "m/s^2"),
    ("LatAccel", TYPE_FLOAT, "m/s^2"),
    ("VertAccel", TYPE_FLOAT, "m/s^2"),
    ("YawRate", TYPE_FLOAT, "rad/s"),
    ("Roll", TYPE_FLOAT, "rad"),
    ("Pitch", TYPE_FLOAT, "rad"),
    ("Lat", TYPE_DOUBLE, "deg"),
    ("Lon", TYPE_DOUBLE, "deg"),
    ("FuelLevelPct", TYPE_FLOAT, "%"),
]
for _corner in ("LF", "RF", "LR", "RR"):
    for _pos in ("L", "M", "R"):
        CHANNELS.append((f"{_corner}temp{_pos}", TYPE_FLOAT, "C"))
    CHANNELS.append((f"{_corner}wearM", TYPE_FLOAT, "%"))
    CHANNELS.append((f"{_corner}pressure", TYPE_FLOAT, "kPa"))


def _layout(channels=None):
    """Assign each channel an offset inside a sample row (naturally aligned)."""
    offset = 0
    layout = []
    for name, vtype, unit in (channels if channels is not None else CHANNELS):
        size = _SIZE[vtype]
        if offset % size:
            offset += size - (offset % size)
        layout.append({"name": name, "type": vtype, "unit": unit, "offset": offset})
        offset += size
    buf_len = offset + (8 - offset % 8) % 8
    return layout, buf_len


def write_ibt(path, channels, rows, session_info, tick_rate=60, lap_count=0):
    """Write a valid .ibt from explicit channel specs and sample rows.

    Shared by the synthetic generator and by the fixture-scrubbing tool, so both
    produce files with identical structure.

    Args:
        path: destination
        channels: list of (name, type_code, unit)
        rows: list of dicts keyed by channel name
        session_info: dict serialised to the YAML header
        tick_rate: samples per second
        lap_count: value for DiskSubHeader.session_lap_count
    """
    layout, buf_len = _layout(channels)
    dt = 1.0 / tick_rate

    info_yaml = yaml.safe_dump(session_info, default_flow_style=False, sort_keys=False)
    info_bytes = info_yaml.encode("latin-1", errors="replace") + b"\x00"

    var_header_bytes = bytearray()
    for item in layout:
        vh = bytearray(VAR_HEADER_SIZE)
        struct.pack_into("iii", vh, 0, item["type"], item["offset"], 1)
        struct.pack_into("?", vh, 12, False)
        struct.pack_into("32s", vh, 16, item["name"].encode("latin-1")[:31])
        struct.pack_into("64s", vh, 48, b"tenths test fixture")
        struct.pack_into("32s", vh, 112, str(item["unit"]).encode("latin-1", "replace")[:31])
        var_header_bytes += vh

    session_info_offset = VAR_HEADER_OFFSET + len(var_header_bytes)
    data_offset = session_info_offset + len(info_bytes)
    pad = (8 - data_offset % 8) % 8
    data_offset += pad

    header = bytearray(DISK_SUB_HEADER_OFFSET)
    struct.pack_into("iiii", header, 0, 2, 1, tick_rate, 0)
    struct.pack_into("ii", header, 16, len(info_bytes), session_info_offset)
    struct.pack_into("ii", header, 24, len(layout), VAR_HEADER_OFFSET)
    struct.pack_into("ii", header, 32, 1, buf_len)
    struct.pack_into("ii", header, 48, len(rows), data_offset)

    disk_sub = bytearray(32)
    struct.pack_into("Q", disk_sub, 0, 0)
    struct.pack_into("d", disk_sub, 8, 0.0)
    struct.pack_into("d", disk_sub, 16, len(rows) * dt)
    struct.pack_into("ii", disk_sub, 24, lap_count, len(rows))

    packers = [(item["offset"], struct.Struct(_FMT[item["type"]]), item["name"])
               for item in layout]

    with open(path, "wb") as f:
        f.write(header)
        f.write(disk_sub)
        f.write(var_header_bytes)
        f.write(info_bytes)
        f.write(b"\x00" * pad)
        row_buf = bytearray(buf_len)
        for row in rows:
            for offset, packer, name in packers:
                packer.pack_into(row_buf, offset, row[name])
            f.write(row_buf)
    return buf_len


def default_session_info(car="Ferrari 296 GT3", track="Test Circuit",
                        event_type="Race", track_length_km=2.0,
                        car_class="GT3 Class", driver_id=999001):
    """Minimal but realistic session-info YAML matching what the analyser reads."""
    return {
        "WeekendInfo": {
            "TrackName": "testcircuit",
            "TrackDisplayName": track,
            "TrackConfigName": None,
            "TrackID": 999,
            "TrackLength": f"{track_length_km:.2f} km",
            "TrackNumTurns": 4,
            "TrackCity": "Testville",
            "TrackState": "TS",
            "TrackCountry": "Testland",
            "TrackPitSpeedLimit": "60.00 kph",
            "TrackLatitude": "0.000000 m",
            "TrackLongitude": "0.000000 m",
            "TrackSurfaceTemp": "30.00 C",
            "TrackAirTemp": "22.00 C",
            "TrackRelativeHumidity": "50 %",
            "EventType": event_type,
            "SeriesID": 1234,
            "SeasonID": 5678,
            "SessionID": 4321,
            "SubSessionID": 87654321,
            "Official": 1,
            "RaceWeek": 3,
        },
        "DriverInfo": {
            "DriverCarIdx": 0,
            "DriverUserID": driver_id,
            "DriverCarRedLine": 8000,
            "DriverCarIdleRPM": 1200,
            "DriverGearboxType": "Sequential",
            "DriverCarFuelMaxLtr": 100.0,
            "Drivers": [{
                "CarIdx": 0,
                "UserName": "Test Driver",
                "CarScreenName": car,
                "CarScreenNameShort": car,
                "CarPath": "testcar",
                "CarID": 77,
                "CarClassShortName": car_class,
                "CarClassID": 42,
            }],
        },
        "SessionInfo": {"Sessions": [{"SessionNum": 0, "SessionType": event_type}]},
    }


class Corner:
    """A corner defined by where it is and how fast it is taken.

    Args:
        pct: apex position as a fraction of the lap (0..1)
        apex_speeds: apex speed in m/s per lap, indexed by position in the laps
                     list. A single float applies to every lap.
        brake_distance_m: length of the braking zone before the apex
        accel_distance_m: distance after the apex to return to straight speed
    """

    def __init__(self, pct, apex_speeds, brake_distance_m=120.0, accel_distance_m=160.0):
        self.pct = pct
        self.apex_speeds = apex_speeds
        self.brake_distance_m = brake_distance_m
        self.accel_distance_m = accel_distance_m

    def apex_speed_for(self, lap_index):
        if isinstance(self.apex_speeds, (int, float)):
            return float(self.apex_speeds)
        return float(self.apex_speeds[lap_index % len(self.apex_speeds)])


def _speed_at(dist_m, track_length_m, corners, lap_index, straight_speed):
    """Speed profile: straight-line speed, dipping linearly to each apex."""
    speed = straight_speed
    for corner in corners:
        apex_m = corner.pct * track_length_m
        apex_speed = corner.apex_speed_for(lap_index)
        delta = dist_m - apex_m
        if -corner.brake_distance_m <= delta <= 0:
            # Braking: straight speed down to apex speed
            frac = (delta + corner.brake_distance_m) / corner.brake_distance_m
            speed = min(speed, straight_speed - (straight_speed - apex_speed) * frac)
        elif 0 < delta <= corner.accel_distance_m:
            # Accelerating out
            frac = delta / corner.accel_distance_m
            speed = min(speed, apex_speed + (straight_speed - apex_speed) * frac)
    return max(speed, 5.0)


def _phase_at(dist_m, track_length_m, corners, lap_index):
    """Return ('brake'|'accel'|'straight', corner) for the given distance."""
    for corner in corners:
        apex_m = corner.pct * track_length_m
        delta = dist_m - apex_m
        if -corner.brake_distance_m <= delta <= 0:
            return "brake", corner
        if 0 < delta <= corner.accel_distance_m:
            return "accel", corner
    return "straight", None


def build_lap_samples(track_length_m, corners, lap_index, straight_speed, tick_rate):
    """Integrate one lap at fixed dt, returning per-sample physical values."""
    dt = 1.0 / tick_rate
    dist = 0.0
    samples = []
    # Hard cap guards against a profile that never completes a lap
    max_samples = tick_rate * 600
    while dist < track_length_m and len(samples) < max_samples:
        speed = _speed_at(dist, track_length_m, corners, lap_index, straight_speed)
        phase, corner = _phase_at(dist, track_length_m, corners, lap_index)
        samples.append({
            "dist": dist,
            "speed": speed,
            "phase": phase,
            "lap_time": len(samples) * dt,
        })
        dist += speed * dt
    return samples


def build_ibt(path, corners, laps=6, track_length_m=2000.0, straight_speed=60.0,
              tick_rate=60, session_info=None, out_lap=True, in_lap=True):
    """Write a synthetic .ibt and return its ground truth.

    Args:
        path: destination file path
        corners: list of Corner
        laps: number of complete timed laps
        track_length_m: lap length
        straight_speed: m/s on the straights
        tick_rate: samples per second
        session_info: dict for the YAML header (default_session_info() if None)
        out_lap / in_lap: add a partial lap before/after so lap validity
                          filtering is exercised the way it is on real files

    Returns:
        dict with 'lap_times', 'apex_speeds' ({lap_number: {corner_index: m/s}}),
        'valid_laps', 'best_lap', 'track_length_m', 'tick_rate', 'path'.
    """
    layout, buf_len = _layout()
    dt = 1.0 / tick_rate

    # ── Build laps ────────────────────────────────────────────────────────────
    lap_blocks = []          # (lap_number, samples, is_complete)
    lap_number = 1

    if out_lap:
        # Partial lap: joins the track halfway round, so MinDistPct is high and
        # get_valid_laps must reject it.
        full = build_lap_samples(track_length_m, corners, 0, straight_speed, tick_rate)
        lap_blocks.append((lap_number, full[len(full) // 2:], False))
        lap_number += 1

    timed_lap_numbers = []
    for i in range(laps):
        samples = build_lap_samples(track_length_m, corners, i, straight_speed, tick_rate)
        lap_blocks.append((lap_number, samples, True))
        timed_lap_numbers.append(lap_number)
        lap_number += 1

    if in_lap:
        full = build_lap_samples(track_length_m, corners, 0, straight_speed, tick_rate)
        lap_blocks.append((lap_number, full[:len(full) // 3], False))

    lap_times = {n: len(s) * dt for n, s, complete in lap_blocks if complete}
    best_lap = min(lap_times, key=lap_times.get) if lap_times else None
    best_time = lap_times[best_lap] if best_lap else 0.0

    apex_speeds = {}
    for idx, n in enumerate(timed_lap_numbers):
        apex_speeds[n] = {ci: c.apex_speed_for(idx) for ci, c in enumerate(corners)}

    # ── Flatten to rows ───────────────────────────────────────────────────────
    rows = []
    session_time = 0.0
    tick = 0
    for lap_num, samples, complete in lap_blocks:
        lap_time_total = len(samples) * dt
        for s in samples:
            pct = s["dist"] / track_length_m
            phase = s["phase"]
            if phase == "brake":
                brake, throttle = 0.85, 0.0
                long_accel, steer = -12.0, 0.15
            elif phase == "accel":
                brake, throttle = 0.0, 0.9
                long_accel, steer = 6.0, 0.35
            else:
                brake, throttle = 0.0, 1.0
                long_accel, steer = 0.5, 0.01
            lat_accel = 14.0 if phase in ("brake", "accel") else 0.3
            rows.append({
                "SessionTime": session_time,
                "SessionTick": tick,
                "Lap": lap_num,
                "LapCompleted": lap_num - 1,
                "LapDist": s["dist"],
                "LapDistPct": pct,
                "LapCurrentLapTime": s["lap_time"],
                # Matches observed real-file behaviour: the final sample of lap N
                # carries lap N's own time, which is what the analyser reads.
                "LapLastLapTime": lap_time_total if complete else -1.0,
                "LapBestLapTime": best_time,
                "LapDeltaToBestLap": 0.0,
                "LapDeltaToOptimalLap": 0.0,
                "Speed": s["speed"],
                "RPM": 1500.0 + s["speed"] * 90.0,
                "Gear": max(1, min(6, int(s["speed"] / 12) + 1)),
                "Throttle": throttle,
                "Brake": brake,
                "SteeringWheelAngle": steer,
                "BrakeABSactive": bool(phase == "brake" and int(s["dist"]) % 37 == 0),
                "BrakeABScutPct": 0.0,
                "LongAccel": long_accel,
                "LatAccel": lat_accel,
                "VertAccel": 9.81,
                "YawRate": 0.4 if phase != "straight" else 0.01,
                "Roll": 0.01,
                "Pitch": 0.01,
                "Lat": 40.0 + (s["dist"] / track_length_m) * 0.01,
                "Lon": -80.0 + (s["dist"] / track_length_m) * 0.01,
                "FuelLevelPct": 0.8,
            })
            for corner_name, base in (("LF", 82.0), ("RF", 85.0), ("LR", 79.0), ("RR", 81.0)):
                rows[-1][f"{corner_name}tempL"] = base - 2.0
                rows[-1][f"{corner_name}tempM"] = base
                rows[-1][f"{corner_name}tempR"] = base + 2.0
                rows[-1][f"{corner_name}wearM"] = 0.95
                rows[-1][f"{corner_name}pressure"] = 170.0
            session_time += dt
            tick += 1

    # ── Serialise ─────────────────────────────────────────────────────────────
    info_yaml = yaml.safe_dump(session_info or default_session_info(
        track_length_km=track_length_m / 1000.0), default_flow_style=False, sort_keys=False)
    info_bytes = info_yaml.encode("latin-1", errors="replace") + b"\x00"

    var_header_bytes = bytearray()
    for item in layout:
        vh = bytearray(VAR_HEADER_SIZE)
        struct.pack_into("iii", vh, 0, item["type"], item["offset"], 1)
        struct.pack_into("?", vh, 12, False)
        struct.pack_into("32s", vh, 16, item["name"].encode("latin-1"))
        struct.pack_into("64s", vh, 48, b"synthetic")
        struct.pack_into("32s", vh, 112, item["unit"].encode("latin-1"))
        var_header_bytes += vh

    session_info_offset = VAR_HEADER_OFFSET + len(var_header_bytes)
    data_offset = session_info_offset + len(info_bytes)
    if data_offset % 8:
        data_offset += 8 - (data_offset % 8)

    header = bytearray(DISK_SUB_HEADER_OFFSET)
    struct.pack_into("iiii", header, 0, 2, 1, tick_rate, 0)
    struct.pack_into("ii", header, 16, len(info_bytes), session_info_offset)
    struct.pack_into("ii", header, 24, len(layout), VAR_HEADER_OFFSET)
    struct.pack_into("ii", header, 32, 1, buf_len)
    struct.pack_into("ii", header, 48, len(rows), data_offset)  # var_buf[0]

    disk_sub = bytearray(32)
    struct.pack_into("Q", disk_sub, 0, 0)
    struct.pack_into("d", disk_sub, 8, 0.0)
    struct.pack_into("d", disk_sub, 16, len(rows) * dt)
    struct.pack_into("ii", disk_sub, 24, len(lap_times), len(rows))

    packers = [(item["offset"], struct.Struct(_FMT[item["type"]]), item["name"])
               for item in layout]

    with open(path, "wb") as f:
        f.write(header)
        f.write(disk_sub)
        f.write(var_header_bytes)
        f.write(info_bytes)
        f.write(b"\x00" * (data_offset - (VAR_HEADER_OFFSET + len(var_header_bytes) + len(info_bytes))))
        row_buf = bytearray(buf_len)
        for row in rows:
            for offset, packer, name in packers:
                packer.pack_into(row_buf, offset, row[name])
            f.write(row_buf)

    return {
        "path": str(path),
        "lap_times": lap_times,
        "apex_speeds": apex_speeds,
        "valid_laps": timed_lap_numbers,
        "best_lap": best_lap,
        "best_time": best_time,
        "track_length_m": track_length_m,
        "tick_rate": tick_rate,
        "corners": corners,
        "sample_count": len(rows),
    }


# ─── Standard test session ────────────────────────────────────────────────────

# Apex speeds (m/s) per lap for the deliberately inconsistent corner.
INCONSISTENT_APEX_SPEEDS_MPS = [20.0, 26.0, 22.0, 24.0, 21.0, 25.0]

# Index of that corner within default_test_corners()
INCONSISTENT_CORNER_INDEX = 2


def default_test_corners():
    """Four corners: three driven identically every lap, one inconsistent.

    Any time loss the analyser reports must therefore land on corner index
    INCONSISTENT_CORNER_INDEX and nowhere else.
    """
    return [
        Corner(pct=0.15, apex_speeds=30.0),
        Corner(pct=0.40, apex_speeds=25.0),
        Corner(pct=0.65, apex_speeds=INCONSISTENT_APEX_SPEEDS_MPS),
        Corner(pct=0.88, apex_speeds=40.0),
    ]


def qualcomm_like_corners():
    """Closely spaced corners reproducing the 2026-07-28 Qualcomm failure mode.

    Corner centres are only a few percent apart on a long lap, which is what
    made the old percentage-based apex window sample the wrong piece of track.
    Every corner here is driven identically on every lap, so any reported
    spread or over-slowing is a corner-attribution bug, not driver variation.
    """
    return [
        Corner(pct=0.117, apex_speeds=24.0, brake_distance_m=140.0, accel_distance_m=180.0),
        Corner(pct=0.181, apex_speeds=23.5, brake_distance_m=140.0, accel_distance_m=180.0),
        Corner(pct=0.324, apex_speeds=37.0, brake_distance_m=140.0, accel_distance_m=180.0),
        Corner(pct=0.468, apex_speeds=25.0, brake_distance_m=140.0, accel_distance_m=180.0),
        Corner(pct=0.555, apex_speeds=24.5, brake_distance_m=140.0, accel_distance_m=180.0),
        Corner(pct=0.694, apex_speeds=18.0, brake_distance_m=140.0, accel_distance_m=180.0),
        Corner(pct=0.783, apex_speeds=38.0, brake_distance_m=140.0, accel_distance_m=180.0),
        Corner(pct=0.890, apex_speeds=22.0, brake_distance_m=140.0, accel_distance_m=180.0),
    ]
