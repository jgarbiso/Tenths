"""
Tenths — iRacing Race Result Parser
======================================
Parses iRacing event result files (CSV or JSON) and extracts
key race data for session notes integration.

Usage:
    python -m tenths.results "path/to/eventresult_12345_0.csv"
    python -m tenths.results "path/to/eventresult-12345.json"

Supports both CSV export and JSON export from iRacing.
"""

import csv
import json
import os
import sys


def parse_csv_result(filepath, my_cust_id=None):
    """Parse an iRacing CSV event result file.

    Args:
        filepath: path to the eventresult CSV
        my_cust_id: the driver's iRacing customer ID (from the .ibt session_info
                    'driver_id'). Used to identify which result row is the user's.
                    If None, my_result will be None.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Need at least the metadata header + values + a results header
    if len(lines) < 2:
        return None

    # First line pair is race metadata
    # Line 1: headers for metadata
    # Line 2: metadata values
    meta_reader = csv.DictReader([lines[0], lines[1]])
    meta = next(meta_reader)

    # Find the results section (skip blank line after metadata)
    # Results start at line 3 (header) and line 4+ (data)
    result_lines = [l for l in lines[3:] if l.strip()]
    if not result_lines:
        return None

    reader = csv.DictReader(result_lines)
    results = list(reader)

    # Build structured output
    race_data = {
        'source': 'csv',
        'filepath': filepath,
        'track': meta.get('Track', ''),
        'series': meta.get('Series', ''),
        'season_year': meta.get('Season Year', ''),
        'season_quarter': meta.get('Season Quarter', ''),
        'race_week': meta.get('Race Week', ''),
        'sof': _safe_int(meta.get('Strength of Field', 0)),
        'start_time': meta.get('Start Time', ''),
        'entries': len(results),
        'results': [],
        'my_result': None,
    }

    for r in results:
        entry = {
            'finish_pos': int(r.get('Fin Pos', 0)),
            'name': r.get('Name', ''),
            'car': r.get('Car', ''),
            'car_class': r.get('Car Class', ''),
            'start_pos': int(r.get('Start Pos', 0)),
            'laps_completed': int(r.get('Laps Comp', 0)),
            'incidents': int(r.get('Inc', 0)),
            'interval': r.get('Interval', ''),
            'avg_lap_time': r.get('Average Lap Time', ''),
            'fastest_lap_time': r.get('Fastest Lap Time', ''),
            'fastest_lap_num': r.get('Fast Lap#', ''),
            'cust_id': int(r.get('Cust ID', 0)),
            'old_irating': int(r.get('Old iRating', 0)) if r.get('Old iRating') else 0,
            'new_irating': int(r.get('New iRating', 0)) if r.get('New iRating') else 0,
            'old_license_level': int(r.get('Old License Level', 0)) if r.get('Old License Level') else 0,
            'old_license_sub': int(r.get('Old License Sub-Level', 0)) if r.get('Old License Sub-Level') else 0,
            'new_license_level': int(r.get('New License Level', 0)) if r.get('New License Level') else 0,
            'new_license_sub': int(r.get('New License Sub-Level', 0)) if r.get('New License Sub-Level') else 0,
            'reason_out': r.get('Out', ''),
        }
        race_data['results'].append(entry)

        if my_cust_id is not None and entry['cust_id'] == my_cust_id:
            race_data['my_result'] = entry

    return race_data


def parse_json_result(filepath, my_cust_id=None):
    """Parse an iRacing JSON event result file.

    Args:
        filepath: path to the eventresult JSON
        my_cust_id: the driver's iRacing customer ID (from the .ibt session_info
                    'driver_id'). If None, my_result will be None.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    info = data.get('data', data)  # Handle both wrapped and unwrapped formats

    # Find the RACE session
    race_session = None
    for session in info.get('session_results', []):
        if session.get('simsession_name') == 'RACE':
            race_session = session
            break

    if not race_session:
        return None

    results_raw = sorted(race_session.get('results', []), key=lambda x: x.get('finish_position', 99))

    race_data = {
        'source': 'json',
        'filepath': filepath,
        'track': '',  # Not directly in JSON race results
        'series': info.get('series_name', ''),
        'season_year': info.get('season_year', ''),
        'season_quarter': info.get('season_quarter', ''),
        'race_week': info.get('race_week_num', ''),
        'sof': info.get('event_strength_of_field', 0),
        'start_time': info.get('end_time', ''),
        'entries': len(results_raw),
        'laps_complete': info.get('event_laps_complete', 0),
        'results': [],
        'my_result': None,
    }

    for r in results_raw:
        avg_lap = r.get('average_lap', 0)
        best_lap = r.get('best_lap_time', 0)
        entry = {
            'finish_pos': r.get('finish_position', 0) + 1,  # JSON is 0-indexed
            'name': r.get('display_name', ''),
            'car': r.get('car_name', '') if 'car_name' in r else '',
            'car_class': r.get('car_class_short_name', ''),
            'start_pos': r.get('starting_position', 0) + 1,
            'laps_completed': r.get('laps_complete', 0),
            'incidents': r.get('incidents', 0),
            'interval': str(r.get('interval', '')),
            'avg_lap_time': f"{avg_lap/10000:.3f}" if avg_lap > 0 else '',
            'fastest_lap_time': f"{best_lap/10000:.3f}" if best_lap > 0 else '',
            'fastest_lap_num': str(r.get('best_lap_num', '')),
            'cust_id': r.get('cust_id', 0),
            'old_irating': r.get('oldi_rating', 0),
            'new_irating': r.get('newi_rating', 0),
            'old_license_level': r.get('old_license_level', 0),
            'old_license_sub': r.get('old_sub_level', 0),
            'new_license_level': r.get('new_license_level', 0),
            'new_license_sub': r.get('new_sub_level', 0),
            'reason_out': r.get('reason_out', ''),
        }
        race_data['results'].append(entry)

        if my_cust_id is not None and entry['cust_id'] == my_cust_id:
            race_data['my_result'] = entry

    return race_data


def _safe_int(value, default=0):
    """Convert to int, returning default on failure (handles blank/malformed fields)."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_result(filepath, my_cust_id=None):
    """Auto-detect format and parse.

    Args:
        filepath: path to the eventresult file (.csv or .json)
        my_cust_id: the driver's iRacing customer ID from the .ibt session_info
                    ('driver_id'). Required to identify the user's own result row.
    """
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return None

    try:
        if filepath.endswith('.csv'):
            return parse_csv_result(filepath, my_cust_id=my_cust_id)
        elif filepath.endswith('.json'):
            return parse_json_result(filepath, my_cust_id=my_cust_id)
        else:
            print(f"Unknown format: {filepath}")
            return None
    except (IndexError, ValueError, KeyError, csv.Error) as e:
        print(f"Could not parse result file ({os.path.basename(filepath)}): {e}")
        return None


def format_lap_time(time_str):
    """Convert time string or seconds to M:SS.sss format."""
    if not time_str:
        return "N/A"
    try:
        # If it's already in M:SS.sss format
        if ':' in str(time_str):
            return time_str
        # If it's seconds as a string/float
        secs = float(time_str)
        if secs <= 0:
            return "N/A"
        mins = int(secs // 60)
        remainder = secs % 60
        return f"{mins}:{remainder:06.3f}"
    except (ValueError, TypeError):
        return str(time_str) if time_str else "N/A"


def generate_race_context_markdown(race_data):
    """Generate the Race Result Context section for session notes."""
    if not race_data or not race_data.get('my_result'):
        return ""

    me = race_data['my_result']
    results = race_data['results']
    lines = []

    lines.append("## Race Result")
    lines.append("")
    lines.append(f"- **Series:** {race_data['series']}")
    lines.append(f"- **SOF:** {race_data['sof']}")
    lines.append(f"- **Started:** P{me['start_pos']} / {race_data['entries']} cars")
    lines.append(f"- **Finished:** P{me['finish_pos']} / {race_data['entries']} ({me['laps_completed']} laps, {me['incidents']} incidents)")
    if me['old_irating'] and me['new_irating']:
        delta = me['new_irating'] - me['old_irating']
        lines.append(f"- **iRating:** {me['old_irating']} → {me['new_irating']} ({delta:+d})")
    lines.append("")

    # Top results table (top 3 + drivers within 5s of you + you)
    lines.append("| Pos | Driver | Car | Avg Lap | Fast Lap | Inc |")
    lines.append("|---|---|---|---|---|---|")

    my_cust_id = me['cust_id']

    show_indices = set()
    # Always show top 3
    for i in range(min(3, len(results))):
        show_indices.add(i)
    # Always show you
    for i, r in enumerate(results):
        if r['cust_id'] == my_cust_id:
            show_indices.add(i)
            # Show car ahead and behind
            if i > 0:
                show_indices.add(i - 1)
            if i < len(results) - 1:
                show_indices.add(i + 1)

    shown_last = -1
    for i in sorted(show_indices):
        if shown_last >= 0 and i - shown_last > 1:
            lines.append("| ... | | | | | |")
        r = results[i]
        bold = "**" if r['cust_id'] == my_cust_id else ""
        avg = format_lap_time(r['avg_lap_time'])
        fast = format_lap_time(r['fastest_lap_time'])
        lines.append(f"| {bold}P{r['finish_pos']}{bold} | {bold}{r['name']}{bold} | {r['car']} | {avg} | {fast} | {r['incidents']} |")
        shown_last = i

    lines.append("")

    # Gap analysis
    my_pos = me['finish_pos']
    if my_pos > 1:
        winner = results[0]
        lines.append(f"**Gap to winner:** {me['interval']}")
    if my_pos > 1 and my_pos <= len(results):
        car_ahead = results[my_pos - 2]  # -2 because 1-indexed and want pos-1
        lines.append(f"**Gap to P{my_pos-1}:** {car_ahead['name']}")
    if my_pos < len(results):
        car_behind = results[my_pos]  # my_pos index = car behind (0-indexed list)
        lines.append(f"**Gap from P{my_pos+1}:** {car_behind['name']}")

    my_fast = format_lap_time(me['fastest_lap_time'])
    winner_fast = format_lap_time(results[0]['fastest_lap_time']) if results else "N/A"
    lines.append(f"**Your fast lap:** {my_fast} vs winner's {winner_fast}")
    lines.append("")

    return "\n".join(lines)


def print_summary(race_data):
    """Print a summary to stdout."""
    if not race_data:
        print("No data to display.")
        return

    me = race_data.get('my_result')
    results = race_data['results']

    print(f"\n{'='*60}")
    print(f"RACE RESULT — {race_data['track'] or race_data['series']}")
    print(f"{'='*60}")
    print(f"  SOF: {race_data['sof']}  |  Entries: {race_data['entries']}")

    if me:
        print(f"\n  === YOUR RESULT ===")
        print(f"  Finish: P{me['finish_pos']}/{race_data['entries']}")
        print(f"  Start: P{me['start_pos']}")
        print(f"  Laps: {me['laps_completed']}")
        print(f"  Incidents: {me['incidents']}")
        print(f"  Fast lap: {format_lap_time(me['fastest_lap_time'])}")
        print(f"  Avg lap: {format_lap_time(me['avg_lap_time'])}")
        if me['old_irating'] and me['new_irating']:
            delta = me['new_irating'] - me['old_irating']
            print(f"  iRating: {me['old_irating']} -> {me['new_irating']} ({delta:+d})")

    my_cust_id = me['cust_id'] if me else None
    print(f"\n  === FULL RESULTS ===")
    print(f"  {'Pos':>3} {'Name':<25} {'Avg':>8} {'Best':>8} {'Inc':>4}")
    for r in results:
        marker = " ← YOU" if (my_cust_id is not None and r['cust_id'] == my_cust_id) else ""
        avg = format_lap_time(r['avg_lap_time'])
        fast = format_lap_time(r['fastest_lap_time'])
        print(f"  P{r['finish_pos']:>2} {r['name'][:24]:<25} {avg:>8} {fast:>8} {r['incidents']:>4}{marker}")

    print(f"\n{'='*60}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tenths.results <eventresult file> [my_cust_id]")
        print("  Supports .csv and .json formats")
        print("  my_cust_id: your iRacing customer ID (to highlight your result)")
        return

    filepath = sys.argv[1]
    my_cust_id = _safe_int(sys.argv[2], default=None) if len(sys.argv) > 2 else None
    race_data = parse_result(filepath, my_cust_id=my_cust_id)

    if race_data:
        print_summary(race_data)
        # Also generate markdown
        md = generate_race_context_markdown(race_data)
        if md:
            print(f"\n{'='*60}")
            print("MARKDOWN OUTPUT:")
            print(f"{'='*60}")
            print(md)
    else:
        print("Failed to parse results.")


if __name__ == "__main__":
    main()
