"""
Session Summary JSON Generator
================================
Generates a structured, versioned JSON file for each processed session.
This is the stable data contract consumed by:
- Local web dashboard (FastAPI)
- Background service
- Cloud platform upload
- Historical progression analysis

Usage:
    from tenths.summary import generate_session_summary
    summary = generate_session_summary(data, file_info, track_map, race_result)
"""

import json
import os
from datetime import datetime, timezone

from tenths.track_map import get_turn_name

CURRENT_SCHEMA_VERSION = "1.0.0"


def generate_session_summary(data, file_info, track_map, race_result=None):
    """Generate a structured JSON summary from analysis data.

    Args:
        data: dict from analyzer.analyze()
        file_info: dict with car, track, date, time, filename keys
        track_map: track map data from load_track_map()
        race_result: optional dict from results.parse_result()

    Returns:
        JSON-serializable dict containing the complete session summary.
    """
    si = data.get('session_info', {})

    # Car info
    car = {
        'name': si.get('car_screen_name') or file_info['car'].replace('_', ' '),
        'short_name': si.get('car_screen_name_short', ''),
        'path': si.get('car_path', file_info['car']),
        'class': data.get('car_class', 'Touring'),
        'class_short': si.get('car_class_short', ''),
        'id': si.get('car_id', 0),
        'redline_rpm': si.get('driver_car_redline', 0),
        'fuel_max_liters': si.get('driver_car_fuel_max_ltr', 0),
    }

    # Track info
    track = {
        'name': si.get('track_display_name') or file_info['track'].replace('_', ' ').title(),
        'config': si.get('track_config_name', ''),
        'internal_name': si.get('track_name_internal', file_info['track']),
        'id': si.get('track_id', 0),
        'length_m': data.get('track_length_m', 0),
        'num_turns': si.get('track_num_turns', 0),
        'country': si.get('track_country', ''),
    }

    # Session metadata
    session = {
        'type': si.get('event_type', 'Practice'),
        'date': file_info['date'],
        'time': file_info['time'],
        'subsession_id': si.get('subsession_id', 0),
        'series_id': si.get('series_id', 0),
        'official': si.get('official', 0),
    }

    # Best lap
    valid_results = [r for r in data['lap_results'] if r['time'] > 0]
    best_result = min(valid_results, key=lambda x: x['time'])
    cleanest_result = min(valid_results, key=lambda x: x['abs'] if x['time'] < best_result['time'] + 3 else 9999)

    best_lap = {
        'number': best_result['lap'],
        'time_seconds': best_result['time'],
        'time_formatted': _fmt_time(best_result['time']),
        'abs_hits': best_result['abs'],
        'max_speed_mph': best_result['max_speed_mph'],
    }

    # All valid laps
    laps = []
    for r in valid_results:
        laps.append({
            'number': r['lap'],
            'time_seconds': r['time'],
            'time_formatted': _fmt_time(r['time']),
            'abs_hits': r['abs'],
            'max_speed_mph': round(r['max_speed_mph'], 1),
            'is_best': r['lap'] == best_result['lap'],
            'is_cleanest': r == cleanest_result,
        })

    # ABS data
    abs_data = {
        'cleanest_hits': cleanest_result['abs'],
        'cleanest_lap': cleanest_result['lap'],
        'per_lap_totals': data.get('lap_abs_totals', []),
        'trend': data.get('abs_trend', {}),
    }

    # Braking zones with turn names
    braking_zones = []
    for z in data.get('braking_zones', []):
        zone = {
            'turn_name': get_turn_name(track_map, z['pct']),
            'position_pct': round(z['pct'], 1),
            'entry_pct': round(z.get('entry_pct', z['pct']), 1),
            'entry_speed_mph': round(z['entry_mph'], 1),
            'min_speed_mph': round(z['min_mph'], 1),
            'max_brake_pct': round(z['max_brake'], 1),
            'abs_hits': z['abs'],
            'distance_m': round(z.get('dist_m', 0), 0),
            'lat': z.get('lat', 0),
            'lon': z.get('lon', 0),
            'brake_to_shift_s': z.get('brake_to_shift') if z.get('brake_to_shift') is not None and z.get('brake_to_shift') >= 0 else None,
            't2peak_s': z.get('t2peak'),
            'coast_time_s': z.get('coast_time'),
            'turnin_brake_pct': z.get('turnin_brake'),
            'apex_brake_pct': round(z.get('apex_brake', 0), 1),
            'apex_rpm': round(z.get('apex_rpm', 0), 0),
            'max_downshift_rpm': round(z.get('max_ds_rpm', 0), 0),
            'notes': z.get('notes', []),
        }
        braking_zones.append(zone)

    # Corner variance with turn names
    corner_variance = []
    for cv in data.get('corner_variance', []):
        corner_variance.append({
            'turn_name': get_turn_name(track_map, cv['pct']),
            'position_pct': round(cv['pct'], 1),
            'avg_time_s': round(cv['avg'], 3),
            'best_time_s': round(cv['best'], 3),
            'time_loss_s': round(cv['loss'], 3),
            'std_dev_s': round(cv['std'], 3),
            'priority': 'high' if cv['loss'] > 0.5 else ('medium' if cv['loss'] > 0.3 else 'low'),
        })

    # Trail braking
    trail_braking = []
    for tb in data.get('trail_braking', []):
        trail_braking.append({
            'turn_name': get_turn_name(track_map, tb['pct']),
            'position_pct': round(tb['pct'], 1),
            'brake_pct': round(tb['brake'], 1),
            'lateral_g': round(tb['lat_g'], 2),
            'yaw_rate': round(tb['yaw'], 2),
            'diagnosis': tb['diagnosis'],
        })

    # GPS trace (best lap — 200 points)
    gps_trace = data.get('gps_trace', [])

    # Tire temps
    tire_temps = data.get('tire_temps', {})

    # Race result
    race = None
    if race_result and race_result.get('my_result'):
        me = race_result['my_result']
        race = {
            'finish_position': me.get('finish_pos', 0),
            'start_position': me.get('start_pos', 0),
            'field_size': race_result.get('entries', 0),
            'sof': race_result.get('sof', 0),
            'irating_before': me.get('old_irating', 0),
            'irating_after': me.get('new_irating', 0),
            'irating_delta': me.get('new_irating', 0) - me.get('old_irating', 0),
            'incidents': me.get('incidents', 0),
            'laps_completed': me.get('laps_completed', 0),
        }

    # Build the full summary
    summary = {
        'schema_version': CURRENT_SCHEMA_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_file': file_info.get('filename', ''),
        'car': car,
        'track': track,
        'session': session,
        'best_lap': best_lap,
        'laps': laps,
        'abs': abs_data,
        'braking_zones': braking_zones,
        'corner_variance': corner_variance,
        'trail_braking': trail_braking,
        'gps_trace': gps_trace,
        'tire_temps': tire_temps,
        'race_result': race,
        'total_valid_laps': len(data.get('valid_laps', [])),
        'total_recoverable_time_s': round(sum(cv['loss'] for cv in data.get('corner_variance', [])), 3),
    }

    return summary


def write_session_summary(summary, output_dir):
    """Write the session summary to a JSON file.

    Args:
        summary: dict from generate_session_summary()
        output_dir: directory path to write session_summary.json

    Returns:
        Path to the written file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "session_summary.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, default=str)
    return filepath


def _fmt_time(seconds):
    """Format seconds as M:SS.mmm"""
    if seconds <= 0:
        return "N/A"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:06.3f}"


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

def generate_summary_cli():
    """CLI entry point: tenths summary <file.ibt>"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: tenths summary <file.ibt>")
        print("  Generates session_summary.json in the session output directory.")
        return

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    from tenths.analyzer import analyze
    from tenths.track_map import load_track_map
    from tenths.process import parse_filename, find_race_result, TELEMETRY_ROOT

    print(f"Analyzing: {os.path.basename(filepath)}")
    data = analyze(filepath)
    if not data:
        print("No valid laps found.")
        return

    # Parse file info
    file_info = parse_filename(filepath)
    if not file_info:
        basename = os.path.splitext(os.path.basename(filepath))[0]
        file_info = {'car': 'Unknown', 'track': 'Unknown', 'date': 'Unknown', 'time': '00-00-00', 'filename': basename}

    # Load track map
    track_map = load_track_map(file_info['track'])

    # Try to find race result
    race_result = None
    si = data.get('session_info', {})
    result_file = find_race_result(si)
    if result_file:
        from tenths.results import parse_result
        race_result = parse_result(result_file)

    # Generate summary
    summary = generate_session_summary(data, file_info, track_map, race_result)

    # Write to session directory
    session_dir = os.path.join(TELEMETRY_ROOT, file_info['car'], file_info['track'], file_info['date'])
    summary_path = write_session_summary(summary, session_dir)

    print(f"Summary generated: {summary_path}")
    print(f"  Schema version: {summary['schema_version']}")
    print(f"  Best lap: {summary['best_lap']['time_formatted']} (Lap {summary['best_lap']['number']})")
    print(f"  Braking zones: {len(summary['braking_zones'])}")
    print(f"  Corner variance entries: {len(summary['corner_variance'])}")
    if summary['race_result']:
        print(f"  Race: P{summary['race_result']['finish_position']}/{summary['race_result']['field_size']}, iR {summary['race_result']['irating_delta']:+d}")
