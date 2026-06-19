"""
Session Index Generator — POC
================================
Generates a top-level index.html for a car/track directory that lists
all sessions with links to their reports.

Usage:
    from tenths.index_generator import generate_index
    generate_index("c:/path/to/telemetry/bmwm2g87/okayama_full")

    # Or via CLI:
    python -m tenths.cli index "car/track"
"""

import os
import json
import glob
from html import escape


def generate_index(track_dir):
    """Generate an index.html listing all sessions for a car/track.

    Args:
        track_dir: path to the car/track directory (e.g., telemetry/bmwm2g87/okayama_full)

    Returns:
        Path to the generated index.html, or None if no sessions found.
    """
    if not os.path.isdir(track_dir):
        return None

    # Scan for session_summary.json files
    sessions = []
    for root, dirs, files in os.walk(track_dir):
        if 'session_summary.json' in files:
            summary_path = os.path.join(root, 'session_summary.json')
            report_path = os.path.join(root, 'session_report.html')
            try:
                with open(summary_path, 'r', encoding='utf-8') as f:
                    summary = json.load(f)
                sessions.append({
                    'dir': root,
                    'report_exists': os.path.exists(report_path),
                    'report_path': report_path,
                    'date': summary.get('session', {}).get('date', ''),
                    'time': summary.get('session', {}).get('time', ''),
                    'type': summary.get('session', {}).get('type', 'Practice'),
                    'best_lap': summary.get('best_lap', {}).get('time_formatted', '—'),
                    'best_lap_s': summary.get('best_lap', {}).get('time_seconds', 9999),
                    'laps': summary.get('total_valid_laps', 0),
                    'car': summary.get('car', {}).get('name', ''),
                    'track': summary.get('track', {}).get('name', ''),
                    'race_result': summary.get('race_result'),
                })
            except (json.JSONDecodeError, KeyError):
                continue

    if not sessions:
        return None

    # Sort by date + time (most recent first)
    sessions.sort(key=lambda s: (s['date'], s['time']), reverse=True)

    # Get car/track names from most recent session
    car_name = sessions[0]['car'] or os.path.basename(os.path.dirname(track_dir))
    track_name = sessions[0]['track'] or os.path.basename(track_dir)

    # Find all-time best
    best_ever = min(sessions, key=lambda s: s['best_lap_s'])

    # Build HTML
    html = _build_index_html(car_name, track_name, sessions, best_ever, track_dir)

    # Write
    index_path = os.path.join(track_dir, "index.html")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return index_path


def _build_index_html(car, track, sessions, best_ever, track_dir):
    """Build the index HTML page."""
    car_safe = escape(car)
    track_safe = escape(track)
    best_time = escape(best_ever['best_lap'])
    total_sessions = len(sessions)
    total_laps = sum(s['laps'] for s in sessions)

    rows = []
    for s in sessions:
        # Time display
        time_display = s['time'].replace('-', ':') if s['time'] else ''

        # Race result badge
        race_badge = ''
        if s['race_result']:
            pos = s['race_result'].get('finish_position', 0)
            field = s['race_result'].get('field_size', 0)
            ir_delta = s['race_result'].get('irating_delta', 0)
            sign = '+' if ir_delta >= 0 else ''
            ir_color = '#00e676' if ir_delta >= 0 else '#ff1744'
            race_badge = f'<span style="color:{ir_color}">P{pos}/{field} iR {sign}{ir_delta}</span>'

        # Best lap styling
        is_pb = s['best_lap_s'] == best_ever['best_lap_s']
        lap_style = 'color:#00e676;font-weight:700;' if is_pb else ''
        pb_marker = ' ★' if is_pb else ''

        # Report link
        if s['report_exists']:
            rel_path = os.path.relpath(s['report_path'], track_dir).replace('\\', '/')
            link = f'<a href="{rel_path}" style="color:var(--accent-blue);text-decoration:none;">View Report</a>'
        else:
            link = '<span style="color:var(--text-secondary)">—</span>'

        rows.append(f'''<tr>
            <td>{escape(s['date'])}</td>
            <td>{time_display}</td>
            <td>{escape(s['type'])}</td>
            <td style="{lap_style}">{escape(s['best_lap'])}{pb_marker}</td>
            <td>{s['laps']}</td>
            <td>{race_badge}</td>
            <td>{link}</td>
        </tr>''')

    table_rows = '\n'.join(rows)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{car_safe} — {track_safe} — Session History</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-base: #0a0a0f;
            --bg-surface: #12141f;
            --bg-surface-raised: #1a1d2b;
            --border: #2a2d3a;
            --text-primary: #e8eaf0;
            --text-secondary: #8890a4;
            --accent-green: #00e676;
            --accent-red: #ff1744;
            --accent-amber: #ffab00;
            --accent-blue: #448aff;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg-base);
            color: var(--text-primary);
            font-family: 'Inter', system-ui, sans-serif;
            font-size: 13px;
            padding: 24px;
            min-height: 100vh;
        }}
        .header {{
            text-align: center;
            margin-bottom: 32px;
        }}
        .header h1 {{
            font-family: 'Orbitron', monospace;
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 4px;
        }}
        .header .subtitle {{
            font-size: 14px;
            color: var(--text-secondary);
        }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 32px;
            margin: 20px 0;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-value {{
            font-family: 'Orbitron', monospace;
            font-size: 20px;
            font-weight: 700;
            color: var(--accent-green);
        }}
        .stat-label {{
            font-size: 10px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            background: var(--bg-surface);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border);
        }}
        th {{
            text-align: left;
            padding: 10px 12px;
            color: var(--text-secondary);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border);
            font-weight: 500;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #1a1d2b;
        }}
        tr:hover td {{
            background: var(--bg-surface-raised);
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{car_safe}</h1>
        <div class="subtitle">{track_safe}</div>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="stat-value">{best_time}</div>
            <div class="stat-label">All-Time Best</div>
        </div>
        <div class="stat">
            <div class="stat-value">{total_sessions}</div>
            <div class="stat-label">Sessions</div>
        </div>
        <div class="stat">
            <div class="stat-value">{total_laps}</div>
            <div class="stat-label">Total Laps</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Type</th>
                <th>Best Lap</th>
                <th>Laps</th>
                <th>Result</th>
                <th>Report</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
</body>
</html>'''
