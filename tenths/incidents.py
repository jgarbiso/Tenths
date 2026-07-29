"""Analyze specific laps for incident signatures.

Usage:
    python -m tenths.incidents "path/to/file.ibt" 2,3,4
"""
import irsdk
import pandas as pd
import numpy as np
import os
import sys

SAMPLE_RATE = 60


def analyze_incidents(filepath, target_laps):
    """Print incident analysis (speed drops, spins, stops) for the given laps."""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    ibt = irsdk.IBT()
    try:
        ibt.open(filepath)
    except Exception as e:
        print(f"Could not open .ibt file: {e}")
        return

    try:
        channels = ['Lap', 'LapDistPct', 'LapDist', 'Speed', 'Lat', 'Lon',
                    'LatAccel', 'LongAccel', 'YawRate', 'Brake', 'Throttle',
                    'Gear', 'SteeringWheelAngle', 'BrakeABSactive', 'RPM']
        data = {}
        for ch in channels:
            if ch in ibt.var_headers_names:
                data[ch] = ibt.get_all(ch)
    finally:
        ibt.close()

    if not data or 'Lap' not in data:
        print("No usable telemetry channels found in file.")
        return

    df = pd.DataFrame(data)
    df['LapDistPct'] = df['LapDistPct'] * 100
    df['Brake'] = df['Brake'] * 100
    df['Throttle'] = df['Throttle'] * 100
    df['Speed_mph'] = df['Speed'] * 2.237
    for col in ['LatAccel', 'LongAccel']:
        if col in df.columns:
            df[col] = df[col] / 9.80665

    for target_lap in target_laps:
        _analyze_lap(df, target_lap)


def _analyze_lap(df, target_lap):
    """Analyze a single lap for incident signatures."""
    lap = df[df['Lap'] == target_lap].copy().reset_index(drop=True)
    if lap.empty:
        print(f"\n=== LAP {target_lap}: NO DATA ===")
        return

    print(f"\n{'='*60}")
    print(f"LAP {target_lap} ANALYSIS")
    print(f"{'='*60}")
    print(f"  Samples: {len(lap)} | Duration: {len(lap)/SAMPLE_RATE:.1f}s")
    print(f"  Max speed: {lap['Speed_mph'].max():.0f}mph | Min speed: {lap['Speed_mph'].min():.0f}mph")

    # Find sudden speed drops
    lap['speed_delta'] = lap['Speed_mph'].diff(SAMPLE_RATE)
    big_drops = lap[lap['speed_delta'] < -30].copy()
    if not big_drops.empty:
        print(f"\n  SUDDEN SPEED DROPS (>30mph in 1s):")
        big_drops['group'] = (big_drops.index.to_series().diff() > 30).cumsum()
        for g, grp in big_drops.groupby('group'):
            idx = grp.index[0]
            pct = grp['LapDistPct'].iloc[0]
            dist = lap.loc[idx, 'LapDist'] if 'LapDist' in lap.columns else 0
            spd_before = lap.loc[max(0, idx-SAMPLE_RATE), 'Speed_mph']
            spd_min = lap.loc[idx:min(idx+2*SAMPLE_RATE, len(lap)-1), 'Speed_mph'].min()
            lat = grp['Lat'].iloc[0] if 'Lat' in grp.columns else 0
            lon = grp['Lon'].iloc[0] if 'Lon' in grp.columns else 0
            window = lap.loc[max(0, idx-30):min(idx+90, len(lap)-1)]
            max_yaw = window['YawRate'].abs().max() if 'YawRate' in window.columns else 0
            max_lat_g = window['LatAccel'].abs().max() if 'LatAccel' in window.columns else 0
            brake_at = window['Brake'].max()
            steer = window['SteeringWheelAngle'].abs().max() if 'SteeringWheelAngle' in window.columns else 0
            print(f"    {pct:.1f}% ({dist:.0f}m): {spd_before:.0f}→{spd_min:.0f}mph")
            print(f"      GPS: {lat:.6f}, {lon:.6f}")
            print(f"      Yaw:{max_yaw:.2f} | LatG:{max_lat_g:.2f} | Brake:{brake_at:.0f}% | Steer:{steer:.2f}rad")
            if max_yaw > 1.0:
                print(f"      >>> SPIN (yaw > 1.0)")
            elif max_yaw > 0.6:
                print(f"      >>> SNAP/SLIDE (yaw 0.6-1.0)")

    # Car stopped
    stopped = lap[lap['Speed_mph'] < 5]
    if not stopped.empty:
        stopped_groups = (stopped.index.to_series().diff() > 30).cumsum()
        print(f"\n  CAR STOPPED:")
        for g, grp in stopped.groupby(stopped_groups):
            pct = lap.loc[grp.index[0], 'LapDistPct']
            duration = len(grp) / SAMPLE_RATE
            lat = lap.loc[grp.index[0], 'Lat'] if 'Lat' in lap.columns else 0
            lon = lap.loc[grp.index[0], 'Lon'] if 'Lon' in lap.columns else 0
            print(f"    {pct:.1f}% for {duration:.1f}s | GPS: {lat:.6f}, {lon:.6f}")

    # Detailed speed trace every 3%
    print(f"\n  SPEED TRACE (every 3%):")
    print(f"  {'Pct':>5} {'Spd':>6} {'Brk':>5} {'Thr':>5} {'Yaw':>6} {'LatG':>6} {'Steer':>6}")
    for p in range(0, 100, 3):
        s = lap[(lap['LapDistPct'] >= p) & (lap['LapDistPct'] < p+1.5)]
        if not s.empty:
            r = s.iloc[len(s)//2]
            steer = r['SteeringWheelAngle'] if 'SteeringWheelAngle' in lap.columns else 0
            yaw = r['YawRate'] if 'YawRate' in lap.columns else 0
            latg = r['LatAccel'] if 'LatAccel' in lap.columns else 0
            print(f"  {p:4d}% {r['Speed_mph']:5.0f}mph {r['Brake']:4.0f}% {r['Throttle']:4.0f}% {yaw:5.2f} {latg:5.2f}G {steer:5.2f}r")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tenths.incidents <file.ibt> [lap1,lap2,...]")
        print("  Analyzes specific laps for incident signatures (spins, stops, speed drops).")
        print("  Default laps: 2")
        return

    filepath = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            target_laps = [int(x) for x in sys.argv[2].split(',')]
        except ValueError:
            print(f"Invalid lap list: {sys.argv[2]} (expected comma-separated numbers, e.g. 2,3,4)")
            return
    else:
        target_laps = [2]

    analyze_incidents(filepath, target_laps)


if __name__ == "__main__":
    main()
