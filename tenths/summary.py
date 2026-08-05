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

from tenths.jsonio import dump_json
from tenths.track_map import get_turn_name
from tenths.units import celsius_to_fahrenheit, mps_to_mph

CURRENT_SCHEMA_VERSION = "1.0.0"


def _mph(mps, ndigits=1):
    """Convert an analyzer speed (m/s) to mph for the JSON contract.

    The summary is a machine contract read by the index and progression logic,
    so it stays in mph regardless of the user's display-unit preference. The
    analyzer stores SI; this is the conversion boundary. `ndigits=None` leaves
    the value unrounded, matching the fields that were previously unrounded.
    """
    if mps is None:
        return None
    value = mps_to_mph(mps)
    return value if ndigits is None else round(value, ndigits)


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
        # iRacing's own class name, not the internal physics profile
        'class': data.get('car_class_display') or si.get('car_class_short')
                 or data.get('car_class', 'Generic'),
        'physics_profile': data.get('physics_profile') or data.get('car_class', 'Generic'),
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
        'max_speed_mph': _mph(best_result['max_speed_mph'], None),
    }

    # All valid laps
    laps = []
    for r in valid_results:
        laps.append({
            'number': r['lap'],
            'time_seconds': r['time'],
            'time_formatted': _fmt_time(r['time']),
            'abs_hits': r['abs'],
            'max_speed_mph': _mph(r['max_speed_mph']),
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
    exit_metrics_data = data.get('exit_metrics', [])
    apex_data = data.get('apex_consistency', [])
    for i, z in enumerate(data.get('braking_zones', [])):
        zone = {
            'turn_name': get_turn_name(track_map, z['pct']),
            'position_pct': round(z['pct'], 1),
            'entry_pct': round(z.get('entry_pct', z['pct']), 1),
            'entry_speed_mph': _mph(z['entry_mph']),
            'min_speed_mph': _mph(z['min_mph']),
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
        # Merge exit metrics if available
        if i < len(exit_metrics_data):
            zone['thr_on_s'] = exit_metrics_data[i].get('thr_on')
            zone['thr_lag_s'] = exit_metrics_data[i].get('thr_lag')
            zone['brake_linearity'] = exit_metrics_data[i].get('brake_linearity')
        else:
            zone['thr_on_s'] = None
            zone['thr_lag_s'] = None
            zone['brake_linearity'] = None
        # Merge apex consistency + Min Speed Spread (additive schema fields)
        if i < len(apex_data):
            zone['apex_avg_mph'] = _mph(apex_data[i].get('avg_apex_mph'))
            zone['apex_std_mph'] = _mph(apex_data[i].get('std_apex_mph'))
            zone['min_speed_best_mph'] = _mph(apex_data[i].get('min_speed_best_mph'))
            zone['min_speed_worst_mph'] = _mph(apex_data[i].get('min_speed_worst_mph'))
            zone['min_speed_typical_low_mph'] = _mph(apex_data[i].get('min_speed_typical_low_mph'))
            zone['min_speed_typical_high_mph'] = _mph(apex_data[i].get('min_speed_typical_high_mph'))
            zone['min_speed_spread_mph'] = _mph(apex_data[i].get('min_speed_spread_mph'))
            zone['over_braking_mph'] = _mph(apex_data[i].get('over_braking_mph'))
        else:
            zone['apex_avg_mph'] = None
            zone['apex_std_mph'] = None
            zone['min_speed_best_mph'] = None
            zone['min_speed_worst_mph'] = None
            zone['min_speed_typical_low_mph'] = None
            zone['min_speed_typical_high_mph'] = None
            zone['min_speed_spread_mph'] = None
            zone['over_braking_mph'] = None
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

    # GPS trace (best lap — 200 points). The analyzer stores speed in m/s; the
    # contract keeps the historical mph values under the same key.
    gps_trace = []
    for p in data.get('gps_trace', []):
        point = dict(p)
        if point.get('speed_mph') is not None:
            # Unrounded, as the trace has always been stored.
            point['speed_mph'] = _mph(point['speed_mph'], None)
        gps_trace.append(point)

    # Tire temps — analyzer stores °C, the contract keeps °F.
    tire_temps = {}
    for corner, values in (data.get('tire_temps') or {}).items():
        converted = {
            key: (celsius_to_fahrenheit(v) if isinstance(v, (int, float)) else v)
            for key, v in values.items()
        }
        # Average the converted corners, not the converted average — the order
        # the original inline conversion used, so results stay bit-identical.
        parts = [converted.get(k) for k in ('inner', 'mid', 'outer')]
        if all(isinstance(p, (int, float)) for p in parts):
            converted['avg'] = sum(parts) / 3
        tire_temps[corner] = converted

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


# Session output lives at car/track/date/time, but older output sits at
# car/track/date. History discovery must handle both.
_MAX_HISTORY_DEPTH = 3


def _looks_like_date(name):
    return len(name) == 10 and name[4] == '-' and name[7] == '-' and \
        name[:4].isdigit() and name[5:7].isdigit() and name[8:].isdigit()


def _find_track_dir(session_dir):
    """Walk up from a session directory to the car/track directory.

    Handles both layouts: car/track/date/time (watcher output) and the older
    car/track/date. Previously this assumed the parent was always the track
    directory, so for time-level folders it only ever searched the current date
    and never found earlier sessions.
    """
    path = os.path.abspath(session_dir)
    parent = os.path.dirname(path)
    grandparent = os.path.dirname(parent)

    # .../track/date/time -> parent is a date, so the track dir is above it
    if _looks_like_date(os.path.basename(parent)) and os.path.isdir(grandparent):
        return grandparent
    # .../track/date
    if _looks_like_date(os.path.basename(path)) and os.path.isdir(parent):
        return parent
    # Unrecognised shape: treat the parent as the track directory
    return parent if os.path.isdir(parent) else None


def _find_session_summaries(track_dir, max_depth=_MAX_HISTORY_DEPTH):
    """Every session_summary.json beneath a car/track directory.

    Bounded depth keeps this cheap — one car/track tree, not the whole telemetry
    root.
    """
    found = []
    base_depth = os.path.abspath(track_dir).rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(track_dir):
        if os.path.abspath(root).rstrip(os.sep).count(os.sep) - base_depth >= max_depth:
            dirs[:] = []
        if 'session_summary.json' in files:
            found.append(os.path.join(root, 'session_summary.json'))
    return found


def _date_from_path(summary_file, track_dir):
    """Recover a session date from the path when the summary omits it."""
    relative = os.path.relpath(os.path.dirname(summary_file), track_dir)
    for part in relative.split(os.sep):
        if _looks_like_date(part):
            return part
    return relative.split(os.sep)[0] if relative != '.' else ''


def _time_from_path(summary_file):
    """Recover the session time label (HH-MM-SS) from the folder name."""
    name = os.path.basename(os.path.dirname(summary_file))
    parts = name.split('-')
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return name
    return ''


def compute_progression(summary, session_dir):
    """Compute session-over-session progression data.

    Scans sibling session directories (same car/track, earlier dates) for their
    session_summary.json files. Computes deltas vs previous session and vs all-time best.

    Args:
        summary: the current session's summary dict
        session_dir: path to the current session directory (e.g., .../bmwm2csr/winton_national/2026-06-06)

    Returns:
        dict with progression data, or None if no previous sessions found.
        {
            'previous_session': {
                'date': '2026-06-01',
                'best_lap_time_s': 92.5,
            },
            'delta_vs_previous': {
                'lap_time_s': -0.5,          # negative = faster (improved)
                'cleanest_abs': -10,         # negative = fewer (improved)
                'total_recoverable_s': -0.3, # negative = less time loss (improved)
            },
            'alltime_best': {
                'lap_time_s': 90.965,
                'date': '2026-06-06',
                'is_new_pb': True,
            },
            'session_count': 4,              # total sessions at this car/track
            'trend': {
                'lap_times': [92.5, 91.7, 91.2, 90.965],  # ordered oldest→newest
                'dates': ['2026-05-20', '2026-05-25', '2026-06-01', '2026-06-06'],
                'abs_avgs': [150, 120, 80, 82],
            },
        }
    """
    if not session_dir or not os.path.isdir(session_dir):
        return None

    track_dir = _find_track_dir(session_dir)
    if not track_dir:
        return None

    current_date = summary.get('session', {}).get('date', '')
    current_time_label = summary.get('session', {}).get('time', '')
    current_path = os.path.normcase(os.path.abspath(
        os.path.join(session_dir, 'session_summary.json')))
    current_identity = (str(current_date), str(current_time_label or ''))

    previous_sessions = []
    seen_identities = set()
    for summary_file in _find_session_summaries(track_dir):
        # Exclude the current session by path. Comparing directory names against
        # the session date failed for time-level folders, so reprocessing a
        # session made it read its own stale summary as the previous session and
        # report a delta of +0.000s against itself.
        if os.path.normcase(os.path.abspath(summary_file)) == current_path:
            continue

        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                prev = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue   # a corrupt summary must not discard all history
        if not isinstance(prev, dict):
            continue

        try:
            prev_time = float(prev.get('best_lap', {}).get('time_seconds', 0) or 0)
        except (TypeError, ValueError):
            continue
        if prev_time <= 0:
            continue

        session_block = prev.get('session', {}) or {}

        # A session is identified by its date and start time, not its path. The
        # same session can exist in two layouts (legacy car/track/date output
        # alongside the current car/track/date/time output); counting it twice
        # would compare a session against a copy of itself and inflate the
        # session count.
        identity = (
            str(session_block.get('date') or _date_from_path(summary_file, track_dir)),
            str(session_block.get('time') or _time_from_path(summary_file) or ''),
        )
        if identity[1] and identity == current_identity:
            continue
        if identity[1] and identity in seen_identities:
            continue
        seen_identities.add(identity)

        abs_block = prev.get('abs', {}) or {}
        per_lap = [t for t in (abs_block.get('per_lap_totals') or [])
                   if isinstance(t, (int, float))]
        previous_sessions.append({
            'date': session_block.get('date') or _date_from_path(summary_file, track_dir),
            'time': session_block.get('time') or _time_from_path(summary_file),
            'best_lap_time_s': prev_time,
            'cleanest_abs': abs_block.get('cleanest_hits', 0) or 0,
            'total_recoverable_s': prev.get('total_recoverable_time_s', 0) or 0,
            'abs_avg': (sum(per_lap) / len(per_lap)) if per_lap else 0,
        })

    if not previous_sessions:
        return None

    # Oldest first, by full timestamp so multiple sessions on one date order
    # correctly rather than tying on date alone.
    previous_sessions.sort(key=lambda s: (str(s['date']), str(s.get('time') or '')))

    # Only sessions at or before this one count as history. Reprocessing an old
    # session must not treat a later one as its "previous session" — that
    # reported an improvement as a regression. If nothing precedes it, it
    # genuinely is the first session.
    current_sort_key = (str(current_date), str(current_time_label or ''))
    previous_sessions = [s for s in previous_sessions
                         if (str(s['date']), str(s.get('time') or '')) < current_sort_key]
    if not previous_sessions:
        return None

    # Current session stats
    current_time = summary.get('best_lap', {}).get('time_seconds', 0)
    current_abs = summary.get('abs', {}).get('cleanest_hits', 0)
    current_recoverable = summary.get('total_recoverable_time_s', 0)
    current_abs_avg = sum(summary.get('abs', {}).get('per_lap_totals', [])) / max(1, len(summary.get('abs', {}).get('per_lap_totals', [])))

    # Most recent previous session
    most_recent = previous_sessions[-1]

    # All-time best
    all_times = [s['best_lap_time_s'] for s in previous_sessions] + [current_time]
    alltime_best_time = min(all_times) if all_times else current_time
    alltime_best_date = current_date if current_time <= min(s['best_lap_time_s'] for s in previous_sessions) else \
        min(previous_sessions, key=lambda s: s['best_lap_time_s'])['date']

    # Build trend arrays (including current session at the end)
    trend_times = [s['best_lap_time_s'] for s in previous_sessions] + [current_time]
    trend_dates = [s['date'] for s in previous_sessions] + [current_date]
    trend_abs = [s['abs_avg'] for s in previous_sessions] + [current_abs_avg]

    progression = {
        'previous_session': {
            'date': most_recent['date'],
            # Included so two sessions on the same date are distinguishable
            'time': most_recent.get('time', ''),
            'best_lap_time_s': most_recent['best_lap_time_s'],
        },
        'delta_vs_previous': {
            'lap_time_s': round(current_time - most_recent['best_lap_time_s'], 3),
            'cleanest_abs': current_abs - most_recent['cleanest_abs'],
            'total_recoverable_s': round(current_recoverable - most_recent['total_recoverable_s'], 3),
        },
        'alltime_best': {
            'lap_time_s': alltime_best_time,
            'date': alltime_best_date,
            'is_new_pb': current_time <= alltime_best_time,
        },
        'session_count': len(previous_sessions) + 1,
        'trend': {
            'lap_times': [round(t, 3) for t in trend_times],
            'dates': trend_dates,
            'abs_avgs': [round(a, 1) for a in trend_abs],
        },
    }

    return progression


def write_session_summary(summary, output_dir):
    """Write the session summary to a JSON file.

    Also computes and attaches session progression data if previous sessions exist.

    Args:
        summary: dict from generate_session_summary()
        output_dir: directory path to write session_summary.json

    Returns:
        Path to the written file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Compute progression (references sibling session directories)
    progression = compute_progression(summary, output_dir)
    if progression:
        summary['progression'] = progression
    else:
        summary['progression'] = None

    filepath = os.path.join(output_dir, "session_summary.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        # Normalised rather than default=str: a NumPy bool written as "False"
        # is truthy in JavaScript and produced false "New PB" badges.
        dump_json(summary, f, indent=2)
    return filepath


def _fmt_time(seconds):
    """Format seconds as M:SS.mmm"""
    if seconds <= 0:
        return "N/A"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:06.3f}"


# ─── Schema Migration System ─────────────────────────────────────────────────

# Migration registry: maps (from_version, to_version) -> transform function.
# Each migration receives the full summary dict and returns the modified dict.
# Migrations are applied sequentially: 1.0.0 → 1.1.0 → 1.2.0 etc.
MIGRATIONS = {
    # Example (uncomment when first migration is needed):
    # ("1.0.0", "1.1.0"): _migrate_1_0_0_to_1_1_0,
}

# Ordered list of all schema versions (oldest first)
SCHEMA_VERSIONS = ["1.0.0"]


def migrate_summary(filepath):
    """Read a session_summary.json, migrate to current schema, write back.

    Args:
        filepath: path to session_summary.json file

    Returns:
        tuple (migrated: bool, from_version: str, to_version: str)
        Returns (False, version, version) if already at current version.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        summary = json.load(f)

    file_version = summary.get('schema_version', '0.0.0')

    if file_version == CURRENT_SCHEMA_VERSION:
        return False, file_version, file_version

    # Apply migrations sequentially
    current = file_version
    for i, version in enumerate(SCHEMA_VERSIONS):
        if version == current and i + 1 < len(SCHEMA_VERSIONS):
            next_version = SCHEMA_VERSIONS[i + 1]
            migration_key = (current, next_version)
            if migration_key in MIGRATIONS:
                summary = MIGRATIONS[migration_key](summary)
                summary['schema_version'] = next_version
                current = next_version
            else:
                # No migration path — force-stamp current version
                break

    # If we couldn't migrate all the way, stamp current version anyway
    # (additive changes don't need explicit migration — missing fields = null)
    original_version = file_version
    summary['schema_version'] = CURRENT_SCHEMA_VERSION

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        dump_json(summary, f, indent=2)

    return True, original_version, CURRENT_SCHEMA_VERSION


def migrate_directory(directory, recursive=True):
    """Find and migrate all session_summary.json files under a directory.

    Args:
        directory: root directory to scan
        recursive: if True, search subdirectories

    Returns:
        list of (filepath, migrated, from_version, to_version) tuples
    """
    results = []

    if recursive:
        for root, dirs, files in os.walk(directory):
            if 'session_summary.json' in files:
                filepath = os.path.join(root, 'session_summary.json')
                migrated, from_v, to_v = migrate_summary(filepath)
                results.append((filepath, migrated, from_v, to_v))
    else:
        filepath = os.path.join(directory, 'session_summary.json')
        if os.path.exists(filepath):
            migrated, from_v, to_v = migrate_summary(filepath)
            results.append((filepath, migrated, from_v, to_v))

    return results


# ─── CLI Entry Points ─────────────────────────────────────────────────────────

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
        race_result = parse_result(result_file, my_cust_id=si.get('driver_id'))

    # Generate summary
    summary = generate_session_summary(data, file_info, track_map, race_result)

    # Write to session directory
    from tenths.config import session_output_dir
    session_dir = session_output_dir(TELEMETRY_ROOT, file_info['car'], file_info['track'],
                                     file_info['date'], file_info['time'])
    summary_path = write_session_summary(summary, session_dir)

    print(f"Summary generated: {summary_path}")
    print(f"  Schema version: {summary['schema_version']}")
    print(f"  Best lap: {summary['best_lap']['time_formatted']} (Lap {summary['best_lap']['number']})")
    print(f"  Braking zones: {len(summary['braking_zones'])}")
    print(f"  Corner variance entries: {len(summary['corner_variance'])}")
    if summary['race_result']:
        print(f"  Race: P{summary['race_result']['finish_position']}/{summary['race_result']['field_size']}, iR {summary['race_result']['irating_delta']:+d}")


def migrate_cli():
    """CLI entry point: tenths migrate [path]"""
    import sys

    # Default to telemetry root
    from tenths.process import TELEMETRY_ROOT
    target = sys.argv[1] if len(sys.argv) > 1 else TELEMETRY_ROOT

    if not os.path.exists(target):
        print(f"Path not found: {target}")
        return

    print(f"Scanning for session_summary.json files in: {target}")
    print(f"Current schema version: {CURRENT_SCHEMA_VERSION}")
    print()

    results = migrate_directory(target)

    if not results:
        print("No session_summary.json files found.")
        return

    migrated_count = sum(1 for _, m, _, _ in results if m)
    print(f"Found {len(results)} file(s):")
    for filepath, migrated, from_v, to_v in results:
        rel_path = os.path.relpath(filepath, target)
        if migrated:
            print(f"  ✅ {rel_path}: {from_v} → {to_v}")
        else:
            print(f"  ── {rel_path}: {from_v} (current)")

    print(f"\nMigrated: {migrated_count} / {len(results)} files")
