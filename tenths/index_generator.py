"""
Session Index Generator — Master Session Browser
==================================================
Generates a master index.html at the telemetry root that lists ALL sessions
across all cars and tracks with filtering and grouping capabilities.

Usage:
    from tenths.index_generator import generate_master_index
    generate_master_index()

    # Or via CLI:
    python -m tenths.cli index
"""

import os
import json
import glob
from html import escape as html_escape

from tenths.config import TELEMETRY_ROOT


def generate_master_index(telemetry_root=None):
    """Generate a master index.html listing all sessions across all cars/tracks.

    Args:
        telemetry_root: path to telemetry root (defaults to config)

    Returns:
        Path to the generated index.html, or None if no sessions found.
    """
    root = telemetry_root or TELEMETRY_ROOT
    if not os.path.isdir(root):
        return None

    # Scan for all session_summary.json files
    sessions = []
    for summary_path in glob.glob(os.path.join(root, "**", "session_summary.json"), recursive=True):
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)

            report_path = os.path.join(os.path.dirname(summary_path), 'session_report.html')

            sessions.append({
                'summary_path': summary_path,
                'report_path': report_path,
                'report_exists': os.path.exists(report_path),
                'date': summary.get('session', {}).get('date', ''),
                'time': summary.get('session', {}).get('time', ''),
                'type': summary.get('session', {}).get('type', 'Practice'),
                'best_lap': summary.get('best_lap', {}).get('time_formatted', '—'),
                'best_lap_s': summary.get('best_lap', {}).get('time_seconds', 9999),
                'laps': summary.get('total_valid_laps', 0),
                'car': summary.get('car', {}).get('name', 'Unknown'),
                'track': summary.get('track', {}).get('name', 'Unknown'),
                'track_config': summary.get('track', {}).get('config', ''),
                'race_result': summary.get('race_result'),
            })
        except (json.JSONDecodeError, KeyError, IOError):
            continue

    if not sessions:
        return None

    # Sort by date + time (newest first)
    sessions.sort(key=lambda s: (s['date'], s['time']), reverse=True)

    # Extract unique cars and tracks for filter buttons
    cars = sorted(set(s['car'] for s in sessions))
    tracks = sorted(set(s['track'] for s in sessions))

    # Build HTML
    html = _build_master_html(sessions, cars, tracks, root)

    # Write
    index_path = os.path.join(root, "index.html")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return index_path


def _build_master_html(sessions, cars, tracks, root):
    """Build the master index HTML."""

    total_sessions = len(sessions)
    total_laps = sum(s['laps'] for s in sessions)
    best_ever = min(sessions, key=lambda s: s['best_lap_s'])
    unique_tracks = len(tracks)

    # Build session rows as JSON for JS filtering
    sessions_json = json.dumps([{
        'date': s['date'],
        'time': s['time'],
        'type': s['type'],
        'best_lap': s['best_lap'],
        'best_lap_s': s['best_lap_s'],
        'laps': s['laps'],
        'car': s['car'],
        'track': s['track'],
        'track_config': s['track_config'],
        'report_path': os.path.relpath(s['report_path'], root).replace('\\', '/') if s['report_exists'] else '',
        'race_pos': s['race_result']['finish_position'] if s['race_result'] else 0,
        'race_field': s['race_result']['field_size'] if s['race_result'] else 0,
        'race_ir': s['race_result']['irating_delta'] if s['race_result'] else 0,
    } for s in sessions])

    cars_json = json.dumps(cars)
    tracks_json = json.dumps(tracks)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tenths — Session Browser</title>
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
            margin-bottom: 24px;
        }}
        .header h1 {{
            font-family: 'Orbitron', monospace;
            font-size: 28px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 4px;
        }}
        .header .subtitle {{
            font-size: 13px;
            color: var(--text-secondary);
        }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 40px;
            margin: 20px 0 24px 0;
        }}
        .stat {{ text-align: center; }}
        .stat-value {{
            font-family: 'Orbitron', monospace;
            font-size: 18px;
            font-weight: 700;
            color: var(--accent-green);
        }}
        .stat-label {{
            font-size: 10px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .filters {{
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .filter-label {{
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-right: 4px;
        }}
        .filter-btn {{
            padding: 5px 12px;
            font-size: 11px;
            font-family: inherit;
            background: var(--bg-surface);
            color: var(--text-secondary);
            border: 1px solid var(--border);
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s;
        }}
        .filter-btn:hover {{ border-color: var(--accent-blue); color: var(--text-primary); }}
        .filter-btn.active {{
            border-color: var(--accent-blue);
            background: #448aff18;
            color: var(--accent-blue);
            font-weight: 600;
        }}
        .divider {{
            width: 1px;
            height: 20px;
            background: var(--border);
            margin: 0 8px;
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
            cursor: pointer;
        }}
        th:hover {{ color: var(--text-primary); }}
        td {{
            padding: 9px 12px;
            border-bottom: 1px solid #1a1d2b;
        }}
        tr:hover td {{ background: var(--bg-surface-raised); }}
        .badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 600;
        }}
        .badge-race {{ background: #ff174420; color: var(--accent-red); }}
        .badge-practice {{ background: #00e67620; color: var(--accent-green); }}
        .badge-test {{ background: #ffab0020; color: var(--accent-amber); }}
        .badge-qualify {{ background: #448aff20; color: var(--accent-blue); }}
        a {{ color: var(--accent-blue); text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .empty {{ text-align: center; padding: 40px; color: var(--text-secondary); }}
        .count {{ font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>TENTHS</h1>
        <div class="subtitle">Session Browser</div>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="stat-value">{html_escape(best_ever['best_lap'])}</div>
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
        <div class="stat">
            <div class="stat-value">{unique_tracks}</div>
            <div class="stat-label">Tracks</div>
        </div>
    </div>

    <div class="filters" id="filters">
        <span class="filter-label">Track:</span>
        <button class="filter-btn active" data-filter="track" data-value="all">All</button>
        <span class="divider"></span>
        <span class="filter-label">Car:</span>
        <button class="filter-btn active" data-filter="car" data-value="all">All</button>
    </div>

    <div class="count" id="count"></div>
    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Car</th>
                <th>Track</th>
                <th>Type</th>
                <th>Best Lap</th>
                <th>Laps</th>
                <th>Result</th>
                <th>Report</th>
            </tr>
        </thead>
        <tbody id="sessions-body"></tbody>
    </table>

    <script>
const SESSIONS = {sessions_json};
const CARS = {cars_json};
const TRACKS = {tracks_json};

let filterTrack = 'all';
let filterCar = 'all';

// Build filter buttons
function buildFilters() {{
    const container = document.getElementById('filters');

    // Track buttons
    const trackLabel = container.querySelector('[data-filter="track"][data-value="all"]');
    TRACKS.forEach(t => {{
        const btn = document.createElement('button');
        btn.className = 'filter-btn';
        btn.dataset.filter = 'track';
        btn.dataset.value = t;
        btn.textContent = t.length > 25 ? t.substring(0, 22) + '...' : t;
        btn.title = t;
        trackLabel.parentNode.insertBefore(btn, trackLabel.nextSibling.nextSibling);
    }});

    // Car buttons
    const carLabel = container.querySelector('[data-filter="car"][data-value="all"]');
    CARS.forEach(c => {{
        const btn = document.createElement('button');
        btn.className = 'filter-btn';
        btn.dataset.filter = 'car';
        btn.dataset.value = c;
        btn.textContent = c.length > 20 ? c.substring(0, 17) + '...' : c;
        btn.title = c;
        carLabel.parentNode.appendChild(btn);
    }});

    // Click handlers
    container.querySelectorAll('.filter-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
            const filter = btn.dataset.filter;
            const value = btn.dataset.value;

            // Deactivate siblings of same filter type
            container.querySelectorAll(`[data-filter="${{filter}}"]`).forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            if (filter === 'track') filterTrack = value;
            if (filter === 'car') filterCar = value;

            renderTable();
        }});
    }});
}}

function renderTable() {{
    const tbody = document.getElementById('sessions-body');
    const countEl = document.getElementById('count');

    let filtered = SESSIONS;
    if (filterTrack !== 'all') filtered = filtered.filter(s => s.track === filterTrack);
    if (filterCar !== 'all') filtered = filtered.filter(s => s.car === filterCar);

    // Find best lap in filtered set
    const bestInFilter = filtered.length > 0 ? Math.min(...filtered.map(s => s.best_lap_s)) : 9999;

    countEl.textContent = `Showing ${{filtered.length}} of ${{SESSIONS.length}} sessions`;

    if (!filtered.length) {{
        tbody.innerHTML = '<tr><td colspan="9" class="empty">No sessions match filters</td></tr>';
        return;
    }}

    tbody.innerHTML = filtered.map(s => {{
        const timeDisplay = s.time ? s.time.replace(/-/g, ':') : '';
        const isPB = s.best_lap_s === bestInFilter;
        const lapStyle = isPB ? 'color:var(--accent-green);font-weight:700;' : '';
        const pbMark = isPB ? ' ★' : '';

        // Type badge
        const typeClass = s.type.toLowerCase().includes('race') ? 'badge-race' :
                          s.type.toLowerCase().includes('qual') ? 'badge-qualify' :
                          s.type.toLowerCase().includes('test') ? 'badge-test' : 'badge-practice';
        const typeBadge = `<span class="badge ${{typeClass}}">${{s.type}}</span>`;

        // Race result
        let result = '';
        if (s.race_pos > 0) {{
            const irColor = s.race_ir >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            const irSign = s.race_ir >= 0 ? '+' : '';
            result = `P${{s.race_pos}}/${{s.race_field}} <span style="color:${{irColor}}">iR ${{irSign}}${{s.race_ir}}</span>`;
        }}

        // Report link
        const link = s.report_path ? `<a href="${{s.report_path}}">View</a>` : '—';

        return `<tr>
            <td>${{s.date}}</td>
            <td>${{timeDisplay}}</td>
            <td>${{s.car}}</td>
            <td>${{s.track}}</td>
            <td>${{typeBadge}}</td>
            <td style="${{lapStyle}}">${{s.best_lap}}${{pbMark}}</td>
            <td>${{s.laps}}</td>
            <td>${{result}}</td>
            <td>${{link}}</td>
        </tr>`;
    }}).join('');
}}

// Init
buildFilters();
renderTable();
    </script>
</body>
</html>'''
