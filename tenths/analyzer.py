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

# Car class detection — GT4 cars have high-downforce physics requiring
# different braking shape (spike initial brake) and faster downshifts
GT4_CARS = ["bmwm4evogt4", "bmwm4gt4", "amg_gt4", "porsche718gt4", "mclarengt4"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_time(s):
    if s <= 0:
        return "N/A"
    return f"{int(s//60)}:{s%60:06.3f}"

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
        max_spd = ld['Speed'].max() * 2.237
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

def detect_car_class(vehicle):
    """Detect if the car is a GT4 class vehicle for physics-specific diagnostics."""
    vehicle_lower = vehicle.lower().replace(' ', '').replace('-', '')
    for gt4 in GT4_CARS:
        if gt4 in vehicle_lower:
            return "GT4"
    return "Touring"


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
        entry = grp['Speed'].iloc[0] * 2.237
        min_spd = grp['Speed'].min() * 2.237
        max_brk = grp['Brake'].max()
        abs_h = int(grp['BrakeABSactive'].sum())
        flag = " [ABS]" if abs_h > 0 else ""

        if not has_gear:
            print(f"  {pos:5.1f}% {entry:>7.0f}mph {min_spd:>6.0f}mph {max_brk:>7.0f}% {abs_h:>5}{flag}")
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
            if apex_brake > 15 and min_spd > 20:
                notes.append("Over-slowing (Trust GT4 Grip)")
            # GT4: fast downshifts are optimal for engine braking
            if brake_to_shift is not None and brake_to_shift < 0.15:
                notes.append("Early Shift (Protection Risk)")
            if max_ds_rpm > 7500:
                notes.append("Over-rev Risk")
            if apex_rpm < 3500 and min_spd > 20:
                notes.append("Lugging")
        else:
            # Touring car (M2 CS, etc.) — original logic
            if brake_to_shift is not None and brake_to_shift < 0.2:
                notes.append("Early Shift")
            if max_ds_rpm > 7000:
                notes.append("Aggressive Shift")
            if apex_rpm < 3500 and min_spd > 20:
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

            print(f"  {pos:5.1f}% {entry:>7.0f}mph {min_spd:>6.0f}mph {max_brk:>6.0f}% {abs_h:>5} "
                  f"{t2p_str:>7} {coast_str:>6} {turnin_str:>7} {apx_brk_str:>7}  {notes_str}")
        else:
            print(f"  {pos:5.1f}% {entry:>7.0f}mph {min_spd:>6.0f}mph {max_brk:>6.0f}% {abs_h:>5} "
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
        # Convert C to F
        i_f, m_f, o_f = i*9/5+32, m*9/5+32, o*9/5+32
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
        if lat > 1.2 and brk > 30:
            diag = "GOOD — combined load"
        elif brk > 60 and lat < 0.5:
            diag = "Braking straight"
        elif yaw > 0.5 and brk > 20:
            diag = "High yaw — oversteer risk"
        else:
            diag = "Light trail"
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
        entry_spd = grp['Speed'].iloc[0] * 2.237
        min_spd = grp['Speed'].min() * 2.237

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
                spd = row['Speed'] * 2.237
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

    df, sample_rate, vehicle, venue = parse_ibt(filepath)
    car_class = detect_car_class(vehicle)
    valid_laps = get_valid_laps(df)
    if not valid_laps:
        return None

    # Basic lap results
    lap_results = []
    for lap in valid_laps:
        ld = df[df['Lap'] == lap]
        time = ld['LapLastLapTime'].iloc[-1]
        abs_hits = int(ld['BrakeABSactive'].sum())
        max_spd = ld['Speed'].max() * 2.237
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

    # Braking zones (best lap)
    braking_zones = _extract_braking_zones(df, best_lap, vehicle, sample_rate)

    # Trail braking (best lap)
    trail_braking = _extract_trail_braking(df, best_lap)

    # Corner variance
    corner_variance = _extract_corner_variance(df, valid_laps, best_lap)

    # Tire temps
    tire_temps = _extract_tire_temps(df, best_lap)

    # GPS trace
    gps_trace = _extract_gps_trace(df, best_lap)

    # Track length
    track_length = 0
    if 'LapDist' in df.columns:
        best_data = df[df['Lap'] == best_lap]
        track_length = best_data['LapDist'].max()

    return {
        'filepath': filepath,
        'vehicle': vehicle,
        'venue': venue,
        'car_class': car_class,
        'track_length_m': track_length,
        'sample_rate': sample_rate,
        'total_rows': len(df),
        'valid_laps': valid_laps,
        'best_lap': best_lap,
        'worst_lap': worst_lap,
        'lap_results': lap_results,
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
    }


def _extract_braking_zones(df, lap_num, vehicle, sample_rate=60):
    """Extract braking zone data as list of dicts."""
    car_class = detect_car_class(vehicle)
    lap = df[df['Lap'] == lap_num].copy().reset_index(drop=True)

    braking = lap[lap['Brake'] > 50][['LapDistPct','Speed','Brake','BrakeABSactive']].copy()
    if braking.empty:
        return []
    braking['zone'] = (braking['LapDistPct'].diff().abs() > 5).cumsum()

    has_gear = 'Gear' in lap.columns and lap['Gear'].max() > 0
    has_gps = 'Lat' in lap.columns and 'Lon' in lap.columns
    has_dist = 'LapDist' in lap.columns

    zones = []
    for z, grp in braking.groupby('zone'):
        pos = grp['LapDistPct'].mean()
        entry_idx = grp.index[0]
        entry = grp['Speed'].iloc[0] * 2.237
        min_spd = grp['Speed'].min() * 2.237
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
            if zone_data['apex_brake'] > 15 and min_spd > 20:
                notes.append("Over-slowing (Trust GT4 Grip)")
            if zone_data['brake_to_shift'] is not None and zone_data['brake_to_shift'] < 0.15:
                notes.append("Early Shift (Protection Risk)")
            if zone_data['max_ds_rpm'] > 7500:
                notes.append("Over-rev Risk")
            if zone_data['apex_rpm'] < 3500 and min_spd > 20:
                notes.append("Lugging")
        else:
            if zone_data['brake_to_shift'] is not None and zone_data['brake_to_shift'] < 0.2:
                notes.append("Early Shift")
            if zone_data['max_ds_rpm'] > 7000:
                notes.append("Aggressive Shift")
            if zone_data['apex_rpm'] < 3500 and min_spd > 20:
                notes.append("Lugging")
        zone_data['notes'] = notes
        zones.append(zone_data)

    return zones


def _extract_trail_braking(df, lap_num):
    """Extract trail braking data as list of dicts."""
    lap = df[df['Lap'] == lap_num].copy()
    trail = lap[
        (lap['Brake'] > 10) & (lap['SteeringWheelAngle'].abs() > 0.1)
    ][['LapDistPct','Brake','LatAccel','YawRate']].copy()
    if trail.empty:
        return []

    trail['zone'] = (trail['LapDistPct'].diff().abs() > 5).cumsum()
    results = []
    for z, grp in trail.groupby('zone'):
        pos = grp['LapDistPct'].mean()
        brk = grp['Brake'].mean()
        lat = grp['LatAccel'].abs().max()
        yaw = grp['YawRate'].abs().max()
        if lat > 1.2 and brk > 30:
            diag = "Good"
        elif brk > 60 and lat < 0.5:
            diag = "Braking straight"
        elif yaw > 0.5 and brk > 20:
            diag = "High yaw — oversteer risk"
        else:
            diag = "Light trail"
        results.append({'pct': pos, 'brake': brk, 'lat_g': lat, 'yaw': yaw, 'diagnosis': diag})
    return results


def _extract_corner_variance(df, valid_laps, best_lap):
    """Extract corner variance data as list of dicts."""
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

    braking['zone'] = (braking['LapDistPct'].diff().abs() > 5).cumsum()
    zone_centers = braking.groupby('zone')['LapDistPct'].mean().values

    sectors = [(center - 3, center + 8, center) for center in zone_centers]
    sample_rate = 60
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
        temps[corner] = {
            'inner': i*9/5+32, 'mid': m*9/5+32, 'outer': o*9/5+32,
            'avg': (i*9/5+32 + m*9/5+32 + o*9/5+32) / 3
        }
    return temps


def _extract_gps_trace(df, lap_num):
    """Extract GPS trace at 10% intervals."""
    has_gps = 'Lat' in df.columns and 'Lon' in df.columns
    has_dist = 'LapDist' in df.columns
    if not has_gps:
        return []

    lap = df[df['Lap'] == lap_num].copy().reset_index(drop=True)
    trace = []
    for pct_target in range(0, 100, 10):
        section = lap[(lap['LapDistPct'] >= pct_target) & (lap['LapDistPct'] < pct_target + 1)]
        if not section.empty:
            row = section.iloc[0]
            trace.append({
                'pct': pct_target,
                'dist': row['LapDist'] if has_dist else 0,
                'lat': row['Lat'],
                'lon': row['Lon'],
                'speed_mph': row['Speed'] * 2.237,
            })
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
