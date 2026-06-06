"""Analyze specific laps for incident signatures."""
import irsdk
import pandas as pd
import numpy as np
import sys

filepath = sys.argv[1]
target_laps = [int(x) for x in sys.argv[2].split(',')] if len(sys.argv) > 2 else [2]

ibt = irsdk.IBT()
ibt.open(filepath)
channels = ['Lap', 'LapDistPct', 'LapDist', 'Speed', 'Lat', 'Lon',
            'LatAccel', 'LongAccel', 'YawRate', 'Brake', 'Throttle',
            'Gear', 'SteeringWheelAngle', 'BrakeABSactive', 'RPM']
data = {}
for ch in channels:
    if ch in ibt.var_headers_names:
        data[ch] = ibt.get_all(ch)
ibt.close()

df = pd.DataFrame(data)
df['LapDistPct'] = df['LapDistPct'] * 100
df['Brake'] = df['Brake'] * 100
df['Throttle'] = df['Throttle'] * 100
df['Speed_mph'] = df['Speed'] * 2.237
for col in ['LatAccel', 'LongAccel']:
    if col in df.columns:
        df[col] = df[col] / 9.80665

sample_rate = 60

for target_lap in target_laps:
    lap = df[df['Lap'] == target_lap].copy().reset_index(drop=True)
    if lap.empty:
        print(f"\n=== LAP {target_lap}: NO DATA ===")
        continue

    print(f"\n{'='*60}")
    print(f"LAP {target_lap} ANALYSIS")
    print(f"{'='*60}")
    print(f"  Samples: {len(lap)} | Duration: {len(lap)/sample_rate:.1f}s")
    print(f"  Max speed: {lap['Speed_mph'].max():.0f}mph | Min speed: {lap['Speed_mph'].min():.0f}mph")

    # Find sudden speed drops
    lap['speed_delta'] = lap['Speed_mph'].diff(sample_rate)
    big_drops = lap[lap['speed_delta'] < -30].copy()
    if not big_drops.empty:
        print(f"\n  SUDDEN SPEED DROPS (>30mph in 1s):")
        big_drops['group'] = (big_drops.index.to_series().diff() > 30).cumsum()
        for g, grp in big_drops.groupby('group'):
            idx = grp.index[0]
            pct = grp['LapDistPct'].iloc[0]
            dist = lap.loc[idx, 'LapDist'] if 'LapDist' in lap.columns else 0
            spd_before = lap.loc[max(0, idx-sample_rate), 'Speed_mph']
            spd_min = lap.loc[idx:min(idx+2*sample_rate, len(lap)-1), 'Speed_mph'].min()
            lat = grp['Lat'].iloc[0] if 'Lat' in grp.columns else 0
            lon = grp['Lon'].iloc[0] if 'Lon' in grp.columns else 0
            window = lap.loc[max(0,idx-30):min(idx+90, len(lap)-1)]
            max_yaw = window['YawRate'].abs().max()
            max_lat_g = window['LatAccel'].abs().max()
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
            duration = len(grp) / sample_rate
            lat = lap.loc[grp.index[0], 'Lat'] if 'Lat' in lap.columns else 0
            lon = lap.loc[grp.index[0], 'Lon'] if 'Lon' in lap.columns else 0
            print(f"    {pct:.1f}% for {duration:.1f}s | GPS: {lat:.6f}, {lon:.6f}")

    # Detailed speed trace every 3%
    print(f"\n  SPEED TRACE (every 3%):")
    print(f"  {'Pct':>5} {'Spd':>6} {'Brk':>5} {'Thr':>5} {'Yaw':>6} {'LatG':>6} {'Steer':>6}")
    for p in range(0, 100, 3):
        s = lap[(lap['LapDistPct']>=p)&(lap['LapDistPct']<p+1.5)]
        if not s.empty:
            r = s.iloc[len(s)//2]
            steer = r['SteeringWheelAngle'] if 'SteeringWheelAngle' in lap.columns else 0
            print(f"  {p:4d}% {r['Speed_mph']:5.0f}mph {r['Brake']:4.0f}% {r['Throttle']:4.0f}% {r['YawRate']:5.2f} {r['LatAccel']:5.2f}G {steer:5.2f}r")
