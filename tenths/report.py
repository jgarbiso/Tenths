"""
HTML Session Report Generator
==============================
Generates a self-contained HTML report with:
- Track heatmap (Leaflet + Leaflet.hotline)
- Brake trace chart (Chart.js)
- Hover sync between map and chart
- Race result badge
- Data tables (laps, braking zones, corner variance)

All CSS/JS is inline. Opens in any browser with no server.

Usage:
    from tenths.report import generate_report
    html = generate_report(data, file_info, track_map, race_result)
"""

import json
from tenths.track_map import get_turn_name


def generate_report(data, file_info, track_map, race_result=None, progression=None):
    """Generate a self-contained HTML session report.

    Args:
        data: dict from analyzer.analyze()
        file_info: dict with car, track, date, time keys
        track_map: track map data from load_track_map()
        race_result: optional dict from results.parse_result()
        progression: optional dict from compute_progression() — session-over-session
                     progress data (delta vs previous, PB detection, trend)

    Returns:
        Complete HTML string ready to write to file.
    """
    si = data.get('session_info', {})
    car_display = si.get('car_screen_name') or file_info['car'].replace('_', ' ')
    track_display_name = si.get('track_display_name') or file_info['track'].replace('_', ' ').title()
    track_config = si.get('track_config_name', '')
    track_display = f"{track_display_name}, {track_config}" if track_config else track_display_name
    date = file_info['date']

    # Best lap info
    valid_results = [r for r in data['lap_results'] if r['time'] > 0]
    best_result = min(valid_results, key=lambda x: x['time'])
    cleanest_result = min(valid_results, key=lambda x: x['abs'] if x['time'] < best_result['time'] + 3 else 9999)

    # Format best time
    best_time = best_result['time']
    best_time_str = f"{int(best_time//60)}:{best_time%60:06.3f}"

    # Prepare JSON data for JS
    gps_trace = data.get('gps_trace', [])
    braking_zones = data.get('braking_zones', [])

    # Build braking zones with turn names + exit metrics for JS
    braking_zones_js = []
    exit_metrics = data.get('exit_metrics', [])
    apex_consistency = data.get('apex_consistency', [])
    for i, z in enumerate(braking_zones):
        zone_copy = dict(z)
        zone_copy['turn_name'] = get_turn_name(track_map, z['pct'])
        # Merge exit metrics if available
        if i < len(exit_metrics):
            zone_copy['thr_on'] = exit_metrics[i].get('thr_on')
            zone_copy['thr_lag'] = exit_metrics[i].get('thr_lag')
            zone_copy['brake_linearity'] = exit_metrics[i].get('brake_linearity')
            zone_copy['brake_release_curve'] = exit_metrics[i].get('brake_release_curve', [])
            zone_copy['brake_duration_s'] = exit_metrics[i].get('brake_duration_s')
        else:
            zone_copy['thr_on'] = None
            zone_copy['thr_lag'] = None
            zone_copy['brake_linearity'] = None
            zone_copy['brake_release_curve'] = []
            zone_copy['brake_duration_s'] = None
        # Merge apex consistency
        if i < len(apex_consistency):
            zone_copy['apex_std_mph'] = apex_consistency[i].get('std_apex_mph')
            zone_copy['apex_avg_mph'] = apex_consistency[i].get('avg_apex_mph')
        else:
            zone_copy['apex_std_mph'] = None
            zone_copy['apex_avg_mph'] = None
        braking_zones_js.append(zone_copy)

    # Corner variance with turn names
    corner_variance_js = []
    for cv in data.get('corner_variance', []):
        cv_copy = dict(cv)
        cv_copy['turn_name'] = get_turn_name(track_map, cv['pct'])
        corner_variance_js.append(cv_copy)

    # Trail braking with turn names
    trail_braking_js = []
    for tb in data.get('trail_braking', []):
        tb_copy = dict(tb)
        tb_copy['turn_name'] = get_turn_name(track_map, tb['pct'])
        trail_braking_js.append(tb_copy)

    # Race result data
    race_data = None
    if race_result and race_result.get('my_result'):
        me = race_result['my_result']
        race_data = {
            'finish_pos': me.get('finish_pos', 0),
            'start_pos': me.get('start_pos', 0),
            'entries': race_result.get('entries', 0),
            'old_irating': me.get('old_irating', 0),
            'new_irating': me.get('new_irating', 0),
            'ir_delta': me.get('new_irating', 0) - me.get('old_irating', 0),
            'incidents': me.get('incidents', 0),
            'sof': race_result.get('sof', 0),
            'series': si.get('series_id', ''),
        }

    # Embed data as JSON
    # Per-lap brake points with turn names
    per_lap_brake_points_js = []
    for bp in data.get('per_lap_brake_points', []):
        bp_copy = dict(bp)
        bp_copy['turn_name'] = get_turn_name(track_map, bp['zone_pct'])
        per_lap_brake_points_js.append(bp_copy)

    report_data = {
        'car': car_display,
        'track': track_display,
        'date': date,
        'car_class': data.get('car_class', 'Touring'),
        'best_lap': data.get('best_lap', 0),
        'best_time': best_time_str,
        'best_time_seconds': best_time,
        'cleanest_abs': cleanest_result['abs'],
        'cleanest_lap': cleanest_result['lap'],
        'track_length_m': data.get('track_length_m', 0),
        'valid_laps': len(data.get('valid_laps', [])),
        'gps_trace': gps_trace,
        'gps_traces': {str(k): v for k, v in data.get('gps_traces', {}).items()},
        'braking_zones': braking_zones_js,
        'corner_variance': corner_variance_js,
        'trail_braking': trail_braking_js,
        'per_lap_brake_points': per_lap_brake_points_js,
        'exit_metrics_all': data.get('exit_metrics_all', {}),
        'lap_results': valid_results,
        'lap_abs_totals': data.get('lap_abs_totals', []),
        'abs_trend': data.get('abs_trend', {}),
        'tire_temps': data.get('tire_temps', {}),
        'race_result': race_data,
        'progression': progression,
    }

    data_json = json.dumps(report_data, default=str)

    html = _build_html(data_json, car_display, track_display, date, best_time_str, race_data)
    return html


def _build_html(data_json, car, track, date, best_time, race_data):
    """Build the complete HTML document."""
    from html import escape as html_escape

    # Escape all .ibt-sourced strings to prevent HTML injection
    car = html_escape(car)
    track = html_escape(track)
    date = html_escape(date)
    best_time = html_escape(best_time)

    # Race result badge HTML
    race_badge_html = ''
    if race_data:
        pos = race_data['finish_pos']
        entries = race_data['entries']
        ir_delta = race_data['ir_delta']
        ir_color = 'var(--accent-green)' if ir_delta >= 0 else 'var(--accent-red)'
        ir_sign = '+' if ir_delta >= 0 else ''

        # Podium accent colors
        if pos == 1:
            pos_color = 'var(--accent-gold)'
            pos_glow = '#ffd74040'
        elif pos == 2:
            pos_color = 'var(--accent-silver)'
            pos_glow = '#b0bec540'
        elif pos == 3:
            pos_color = 'var(--accent-bronze)'
            pos_glow = '#ff8f0040'
        else:
            pos_color = 'var(--text-primary)'
            pos_glow = 'transparent'

        race_badge_html = f'''
        <div class="race-badge">
            <div class="race-pos" style="color: {pos_color}; text-shadow: 0 0 12px {pos_glow};">P{pos}</div>
            <div class="race-details">
                <div class="race-field">/ {entries} cars</div>
                <div class="race-ir" style="color: {ir_color};">iR {ir_sign}{ir_delta}</div>
            </div>
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{car} — {track} — {date}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
{_get_css()}
{_get_summary_css()}
    </style>
</head>
<body>
    <!-- Header with View Switcher -->
    <header class="header">
        <div class="header-left">
            <h1 class="title">{car}</h1>
            <div class="subtitle">{track} — {date}</div>
        </div>
        <div class="view-switcher" role="tablist">
            <button class="view-tab active" role="tab" aria-selected="true" data-view="summary" tabindex="0">Summary</button>
            <button class="view-tab" role="tab" aria-selected="false" data-view="detailed" tabindex="-1">Detailed</button>
        </div>
        <div class="header-right">
            {race_badge_html}
        </div>
    </header>

    <!-- Summary View (default) -->
    <main id="summary-view" class="view-panel active">
        <div class="summary-container">
            <div class="hero-row" id="summary-heroes"></div>
            <div class="summary-body">
                <div class="summary-left">
                    <div class="next-focus" id="next-focus"></div>
                    <div class="focus-cards" id="focus-cards"></div>
                </div>
                <div class="summary-right">
                    <canvas id="mini-map" width="280" height="280"></canvas>
                </div>
            </div>
        </div>
    </main>

    <!-- Detailed View (existing report) -->
    <main id="detailed-view" class="view-panel">
        <!-- Main Grid -->
        <div class="grid">
            <!-- Track Map -->
            <section class="card map-card">
                <div class="card-header">
                    <h2>Track Map</h2>
                    <div class="map-controls">
                        <span class="rotate-value" style="font-size:9px;color:var(--text-secondary);">Rotate</span>
                        <button class="rotate-btn" data-dir="1" title="Rotate left">↶</button>
                        <span class="rotate-value" id="rotate-label">90°</span>
                        <button class="rotate-btn" data-dir="-1" title="Rotate right">↷</button>
                        <span class="controls-divider"></span>
                        <div class="toggle-group">
                            <button class="toggle-btn active" data-mode="speed">Speed</button>
                            <button class="toggle-btn" data-mode="brake">Brake</button>
                        </div>
                        <span class="controls-divider"></span>
                        <button class="action-btn" id="brake-points-toggle">⊕ Brake Points</button>
                    </div>
                </div>
                <div id="track-map"></div>
                <div class="map-watermark" id="map-watermark"></div>
                <div class="map-zoom">
                    <button class="map-zoom-btn" id="zoom-in" title="Zoom in">+</button>
                    <button class="map-zoom-btn" id="zoom-out" title="Zoom out">−</button>
                </div>
                <div id="brake-points-legend" class="bp-legend" style="display:none;">
                    <span class="bp-legend-title">Brake Points</span>
                    <div class="bp-legend-bar">
                        <span class="bp-legend-label">Early laps</span>
                        <div class="bp-legend-gradient"></div>
                        <span class="bp-legend-label">Late laps</span>
                    </div>
                </div>
            </section>

            <!-- Session Stats -->
            <section class="card stats-card">
                <div class="card-header"><h2>Session</h2></div>
                <div id="stats-grid"></div>
            </section>

            <!-- Telemetry Traces (Stacked Panels — MoTeC style) -->
            <section class="card chart-card">
                <div class="card-header">
                    <div class="telemetry-header-left">
                        <h2>Telemetry</h2>
                        <span id="crosshair-info" class="crosshair-inline"></span>
                    </div>
                    <div class="telemetry-controls">
                        <select id="lap-selector" class="lap-select"></select>
                        <span class="controls-divider"></span>
                        <button id="compare-btn" class="action-btn">⇄ Compare</button>
                        <select id="compare-selector" class="lap-select" style="display:none;border-left:2px solid var(--accent-blue);"></select>
                        <span id="compare-delta" class="compare-delta" style="display:none;"></span>
                        <span class="controls-divider"></span>
                        <div class="chart-legend">
                            <span class="legend-item"><span class="legend-dot" style="background:#00e676"></span>Throttle</span>
                            <span class="legend-item"><span class="legend-dot" style="background:#ff1744"></span>Brake</span>
                            <span class="legend-item"><span class="legend-dot" style="background:#ffab00"></span>Speed</span>
                            <span class="legend-item"><span class="legend-dot" style="background:#448aff"></span>Steering</span>
                        </div>
                    </div>
                </div>
                <div class="trace-stack">
                    <div class="trace-panel trace-panel-tall">
                        <span class="trace-label">Brake / Throttle</span>
                        <canvas id="chart-brake-throttle"></canvas>
                    </div>
                    <div class="trace-panel">
                        <span class="trace-label">Speed</span>
                        <canvas id="chart-speed"></canvas>
                    </div>
                    <div class="trace-panel trace-panel-delta" id="delta-panel" style="display:none;">
                        <span class="trace-label">Speed Delta</span>
                        <canvas id="chart-delta"></canvas>
                    </div>
                    <div class="trace-panel">
                        <span class="trace-label">Steering</span>
                        <canvas id="chart-steering"></canvas>
                    </div>
                </div>
            </section>

            <!-- Brake Release Shapes -->
            <section class="card table-full-width" id="brake-release-section">
                <div class="card-header">
                    <h2>Brake Release Shape</h2>
                    <div class="chart-legend">
                        <span class="legend-item" style="font-size:10px;color:var(--text-secondary)">Linear release = smooth weight transfer = faster rotation</span>
                    </div>
                </div>
                <div class="release-grid" id="brake-release-grid"></div>
            </section>

            <!-- Tables -->
            <section class="card table-card table-full-width" id="braking-zones-table-section">
                <div class="card-header">
                    <h2>Braking Zones</h2>
                </div>
                <div id="braking-table"></div>
            </section>

            <section class="card table-card">
                <div class="card-header">
                    <h2>Corner Variance</h2>
                </div>
                <div id="variance-table"></div>
            </section>

            <section class="card table-card">
                <div class="card-header">
                    <h2>Lap Summary</h2>
                </div>
                <div id="lap-table"></div>
            </section>
        </div>
    </main>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script>
const DATA = {data_json};
    </script>
    <script>
{_get_js()}
    </script>
    <script>
{_get_summary_js()}
    </script>
</body>
</html>'''


def _get_css():
    """Return the complete CSS for the report."""
    return '''
:root {
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
    --accent-gold: #ffd740;
    --accent-silver: #b0bec5;
    --accent-bronze: #ff8f00;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    background: var(--bg-base);
    color: var(--text-primary);
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    font-size: 13px;
    line-height: 1.4;
    padding: 12px;
    min-height: 100vh;
}

/* Header */
.header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 12px;
}
.header-left { flex: 1; }
.header-center { text-align: center; flex: 0 0 auto; padding: 0 24px; }
.header-right { flex: 1; display: flex; justify-content: flex-end; }

.title {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
}
.subtitle {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 2px;
}
.hero-time {
    font-family: 'Orbitron', 'JetBrains Mono', monospace;
    font-size: 34px;
    font-weight: 700;
    color: var(--accent-green);
    text-shadow: 0 0 12px #00e67640;
    letter-spacing: -0.5px;
}
.hero-label {
    font-size: 11px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Race Badge */
.race-badge {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 16px;
    background: var(--bg-surface-raised);
    border: 1px solid var(--border);
    border-radius: 8px;
}
.race-pos {
    font-family: 'Orbitron', 'JetBrains Mono', monospace;
    font-size: 38px;
    font-weight: 900;
}
.race-details {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.race-field {
    font-size: 12px;
    color: var(--text-secondary);
}
.race-ir {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 600;
}

/* Grid Layout */
.grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}
.map-card { grid-column: 1; grid-row: 1; position: relative; }
.stats-card { grid-column: 2; grid-row: 1; }
.chart-card { grid-column: 1 / -1; grid-row: 2; }
.table-card { break-inside: avoid; }
.table-full-width { grid-column: 1 / -1; }

/* Cards */
.card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    overflow: hidden;
}
.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
}
.card-header h2 {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1.5px;
}

/* Map */
#track-map {
    height: 380px;
    background: #000;
    border-radius: 6px;
    border: 1px solid var(--border);
    position: relative;
}
.leaflet-container { background: #000 !important; }
.map-watermark {
    position: absolute;
    bottom: 16px;
    left: 16px;
    font-family: 'Orbitron', monospace;
    font-size: 11px;
    font-weight: 700;
    color: #ffffff30;
    letter-spacing: 2px;
    text-transform: uppercase;
    pointer-events: none;
    z-index: 400;
}
/* Zoom buttons */
.map-zoom {
    position: absolute;
    bottom: 12px;
    right: 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    z-index: 500;
}
.map-zoom-btn {
    width: 28px;
    height: 28px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text-primary);
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s;
    font-family: system-ui;
}
.map-zoom-btn:hover { background: var(--bg-surface-raised); }
.brake-tooltip {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    font-size: 11px !important;
    font-family: 'JetBrains Mono', monospace !important;
    padding: 3px 8px !important;
    border-radius: 4px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5) !important;
}
.brake-tooltip::before { border-top-color: var(--border) !important; }
.corner-label {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #e8eaf0 !important;
    font-size: 10px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 600 !important;
    text-shadow: 0 0 4px #000, 0 0 8px #000, 0 1px 2px #000 !important;
    padding: 0 !important;
    white-space: nowrap !important;
}
.corner-label::before { display: none !important; }
.sf-label {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #ffffff !important;
    font-size: 9px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    text-shadow: 0 0 4px #000, 0 0 8px #000 !important;
    padding: 0 !important;
    letter-spacing: 1px;
}
.sf-label::before { display: none !important; }
.direction-arrow { background: transparent !important; border: none !important; }
.spread-label {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 9px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    text-shadow: 0 0 4px #000, 0 0 8px #000 !important;
    padding: 0 !important;
}
.spread-label::before { display: none !important; }

/* Brake Points Legend */
.bp-legend {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    margin-top: 6px;
    background: var(--bg-base);
    border: 1px solid var(--border);
    border-radius: 6px;
}
.bp-legend-title {
    font-size: 10px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
}
.bp-legend-bar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
}
.bp-legend-gradient {
    height: 8px;
    flex: 1;
    min-width: 80px;
    border-radius: 4px;
    background: linear-gradient(to right, #448aff, #7c6dd8, #b8508a, #e6a030, #ffab00);
}
.bp-legend-label {
    font-size: 9px;
    color: var(--text-secondary);
    white-space: nowrap;
}

/* Toggle Buttons */
.map-controls {
    display: flex;
    align-items: center;
    gap: 8px;
}
.rotate-btn {
    width: 26px;
    height: 26px;
    background: var(--bg-base);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text-primary);
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s;
}
.rotate-btn:hover { background: var(--bg-surface-raised); }
.rotate-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--text-secondary);
    min-width: 30px;
    text-align: center;
}
.toggle-group {
    display: flex;
    gap: 2px;
    background: var(--bg-base);
    border-radius: 4px;
    padding: 2px;
}
.toggle-btn {
    padding: 4px 10px;
    font-size: 11px;
    background: transparent;
    color: var(--text-secondary);
    border: none;
    border-radius: 3px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s;
}
.toggle-btn.active {
    background: var(--bg-surface-raised);
    color: var(--text-primary);
}
.toggle-btn:hover:not(.active) {
    color: var(--text-primary);
}

/* Action Buttons — distinct from mode toggles */
.action-btn {
    padding: 5px 12px;
    font-size: 11px;
    font-family: inherit;
    font-weight: 500;
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--border);
    border-radius: 5px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
}
.action-btn:hover {
    border-color: var(--accent-blue);
    color: var(--text-primary);
}
.action-btn.active {
    border-color: var(--accent-blue);
    background: #448aff18;
    color: var(--accent-blue);
    font-weight: 600;
}

/* Compare delta badge */
.compare-delta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 3px;
    margin-left: 4px;
}
.compare-delta.faster { color: var(--accent-green); background: #00e67615; }
.compare-delta.slower { color: var(--accent-red); background: #ff174415; }

/* Control group separators */
.controls-divider {
    width: 1px;
    height: 20px;
    background: var(--border);
    margin: 0 6px;
}

/* Chart — Stacked Panels */
.release-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 8px;
}
.release-card {
    background: var(--bg-base);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px;
    text-align: center;
}
.release-card-title {
    font-size: 10px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-secondary);
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.release-card-score {
    font-family: 'Orbitron', monospace;
    font-size: 14px;
    font-weight: 700;
    margin-top: 4px;
}
.release-card-label {
    font-size: 9px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.release-card svg {
    display: block;
    margin: 0 auto;
}

.trace-stack {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.trace-panel {
    position: relative;
    height: 150px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg-base);
}
.trace-panel-tall { height: 180px; }
.trace-panel-delta { height: 80px; }
.trace-panel canvas {
    width: 100% !important;
    height: 100% !important;
}
.trace-label {
    position: absolute;
    top: 6px;
    left: 10px;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 600;
    z-index: 10;
    pointer-events: none;
}
.chart-legend {
    display: flex;
    gap: 12px;
}
.telemetry-controls {
    display: flex;
    align-items: center;
    gap: 14px;
}
.lap-select {
    padding: 4px 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    background: var(--bg-base);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    cursor: pointer;
    outline: none;
}
.lap-select:hover { border-color: var(--accent-blue); }
.lap-select option {
    background: var(--bg-surface);
    color: var(--text-primary);
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--text-secondary);
}
.legend-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    table-layout: auto;
}
.table-card { overflow-x: auto; }
th {
    text-align: left;
    padding: 6px 8px;
    color: var(--text-secondary);
    font-weight: 500;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid var(--border);
}
td {
    padding: 5px 8px;
    border-bottom: 1px solid #1a1d2b;
    color: var(--text-primary);
}
tr:hover td {
    background: var(--bg-surface-raised);
}
.num { text-align: right; }
.good { color: var(--accent-green); }
.bad { color: var(--accent-red); }
.warn { color: var(--accent-amber); }
.info { color: var(--accent-blue); }

/* Stats Grid */
#stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}
.stat-item {
    padding: 10px;
    background: var(--bg-base);
    border-radius: 6px;
    border: 1px solid var(--border);
}
.stat-value {
    font-family: 'Orbitron', 'JetBrains Mono', monospace;
    font-size: 18px;
    font-weight: 700;
    color: var(--text-primary);
}
.stat-label {
    font-size: 10px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}

/* Crosshair Info (inline in telemetry header) */
.telemetry-header-left {
    display: flex;
    align-items: center;
    gap: 12px;
}
.crosshair-inline {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-secondary);
    opacity: 0;
    transition: opacity 0.15s;
    white-space: nowrap;
}
.crosshair-inline.visible {
    opacity: 1;
    color: var(--text-primary);
}

/* Responsive */
@media (max-width: 900px) {
    .grid {
        grid-template-columns: 1fr;
    }
    .map-card, .stats-card, .chart-card {
        grid-column: 1;
        grid-row: auto;
    }
    .header {
        flex-direction: column;
        gap: 12px;
        text-align: center;
    }
    .header-right { justify-content: center; }
}
'''


def _get_js():
    """Return the complete JavaScript for the report."""
    return '''
// ─── State ───────────────────────────────────────────────────────────────
let hoverPct = null;
let mapMode = 'speed';  // 'speed' or 'brake'
let mapRotation = 90;   // degrees clockwise, adjustable

// Restore saved rotation for this track
try {
    const savedRot = localStorage.getItem('tenths_rotation_' + (typeof DATA !== 'undefined' ? DATA.track : ''));
    if (savedRot !== null) mapRotation = parseInt(savedRot);
} catch(e) {}
let showBrakePoints = false;
let brakePointsLayer = null;
let selectedLap = null;  // null = best lap (default)
let compareLap = null;   // null = no comparison active
let map, hotline, cursor;
let chart;

// ─── Init ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Update rotation label to match restored value
    const rotLabel = document.getElementById('rotate-label');
    if (rotLabel) rotLabel.textContent = mapRotation + '°';

    initLapSelector();
    renderStats();
    renderTables();
    initMap();
    initChart();
    initToggle();
    startHoverLoop();
});

// ─── Lap Selector ────────────────────────────────────────────────────────
function initLapSelector() {
    const select = document.getElementById('lap-selector');
    const compareSelect = document.getElementById('compare-selector');
    const compareBtn = document.getElementById('compare-btn');
    if (!select || !compareSelect || !compareBtn) return;

    const laps = DATA.lap_results;
    const bestLap = DATA.best_lap;

    // Populate both dropdowns
    [select, compareSelect].forEach(sel => {
        laps.forEach(l => {
            if (l.time <= 0) return;
            const opt = document.createElement('option');
            opt.value = l.lap;
            const timeStr = `${Math.floor(l.time/60)}:${(l.time%60).toFixed(1).padStart(4,'0')}`;
            const marker = l.lap === bestLap ? ' ★ Best' : '';
            opt.textContent = `Lap ${l.lap} — ${timeStr}${marker}`;
            if (sel === select && l.lap === bestLap) opt.selected = true;
            sel.appendChild(opt);
        });
    });

    selectedLap = bestLap;

    // Compare button toggle
    compareBtn.addEventListener('click', () => {
        if (compareLap !== null) {
            // Deactivate comparison
            compareLap = null;
            compareBtn.classList.remove('active');
            compareSelect.style.display = 'none';
            document.getElementById('compare-delta').style.display = 'none';
            document.getElementById('delta-panel').style.display = 'none';
        } else {
            // Activate comparison — pick a different lap
            compareBtn.classList.add('active');
            compareSelect.style.display = '';
            // Default compare to worst time lap
            const worstLap = laps.filter(l => l.time > 0).sort((a,b) => b.time - a.time)[0];
            if (worstLap) {
                compareSelect.value = worstLap.lap;
                compareLap = worstLap.lap;
            }
            document.getElementById('delta-panel').style.display = '';
            updateCompareDelta();
        }
        onLapChange();
    });

    compareSelect.addEventListener('change', () => {
        compareLap = parseInt(compareSelect.value);
        updateCompareDelta();
        onLapChange();
    });

    select.addEventListener('change', () => {
        selectedLap = parseInt(select.value);
        if (compareLap !== null) updateCompareDelta();
        onLapChange();
    });
}

function updateCompareDelta() {
    const deltaEl = document.getElementById('compare-delta');
    if (!deltaEl || compareLap === null) { if (deltaEl) deltaEl.style.display = 'none'; return; }

    const primaryLap = DATA.lap_results.find(l => l.lap === selectedLap);
    const cmpLap = DATA.lap_results.find(l => l.lap === compareLap);
    if (!primaryLap || !cmpLap || primaryLap.time <= 0 || cmpLap.time <= 0) {
        deltaEl.style.display = 'none';
        return;
    }

    const delta = primaryLap.time - cmpLap.time;
    const sign = delta >= 0 ? '+' : '';
    const cls = delta <= 0 ? 'faster' : 'slower';
    deltaEl.textContent = `Δ ${sign}${delta.toFixed(1)}s`;
    deltaEl.className = `compare-delta ${cls}`;
    deltaEl.style.display = '';
}

function getSelectedTrace() {
    const key = String(selectedLap);
    if (DATA.gps_traces && DATA.gps_traces[key]) {
        return DATA.gps_traces[key];
    }
    return DATA.gps_trace;
}

function getCompareTrace() {
    if (compareLap === null) return null;
    const key = String(compareLap);
    if (DATA.gps_traces && DATA.gps_traces[key]) {
        return DATA.gps_traces[key];
    }
    return null;
}

function onLapChange() {
    rebuildMap();
    charts.forEach(c => c.destroy());
    charts = [];
    initChart();
    renderBrakeRelease();
}

// ─── Stats Panel ─────────────────────────────────────────────────────────
function renderStats() {
    const d = DATA;
    const grid = document.getElementById('stats-grid');
    const stats = [
        { value: d.valid_laps, label: 'Valid Laps' },
        { value: d.cleanest_abs, label: 'Cleanest ABS' },
        { value: d.track_length_m > 0 ? (d.track_length_m/1000).toFixed(2) + ' km' : '—', label: 'Track Length' },
        { value: d.car_class, label: 'Car Class' },
    ];

    // ABS trend with sparkline
    if (d.abs_trend && d.abs_trend.delta !== undefined) {
        const delta = Math.round(d.abs_trend.delta);
        const cls = delta < 0 ? 'good' : (delta > 0 ? 'bad' : '');
        const deltaStr = `<span class="${cls}">${delta > 0 ? '+' : ''}${delta}</span>`;

        // Build SVG sparkline from lap_abs_totals
        let sparkline = '';
        if (d.lap_abs_totals && d.lap_abs_totals.length > 1) {
            const vals = d.lap_abs_totals;
            const maxVal = Math.max(...vals) || 1;
            const w = 80, h = 20;
            const points = vals.map((v, i) => {
                const x = (i / (vals.length - 1)) * w;
                const y = h - (v / maxVal) * h;
                return `${x},${y}`;
            }).join(' ');
            const lineColor = delta < 0 ? '#00e676' : (delta > 0 ? '#ff1744' : '#8890a4');
            sparkline = `<svg width="${w}" height="${h}" style="margin-top:4px;display:block;"><polyline points="${points}" fill="none" stroke="${lineColor}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
        }

        stats.push({ value: deltaStr + sparkline, label: 'ABS Trend', html: true });
    }

    stats.push({ value: d.braking_zones.length, label: 'Brake Zones' });

    grid.innerHTML = stats.map(s =>
        `<div class="stat-item">
            <div class="stat-value">${s.html ? s.value : escHtml(String(s.value))}</div>
            <div class="stat-label">${s.label}</div>
        </div>`
    ).join('');
}

// ─── Tables ──────────────────────────────────────────────────────────────
function renderTables() {
    renderBrakingTable();
    renderVarianceTable();
    renderLapTable();
    renderBrakeRelease();
}

function renderBrakingTable() {
    const zones = DATA.braking_zones;
    if (!zones.length) return;

    // Unified table for all car classes
    const headers = '<tr><th>Zone</th><th>Turn</th><th class="num">Entry</th><th class="num">Min</th><th class="num">Apex ±</th><th class="num">ABS</th><th class="num">T2Peak</th><th class="num">Brk Rel</th><th class="num">Brk Dur</th><th class="num">Thr On</th><th class="num">Thr Lag</th><th>Notes</th></tr>';
    const rows = zones.map(z => {
        const absClass = z.abs > 0 ? 'bad' : '';
        const t2p = z.t2peak != null ? z.t2peak.toFixed(2) + 's' : '—';
        const t2pClass = z.t2peak != null ? (z.t2peak <= 0.4 ? 'good' : (z.t2peak <= 0.55 ? 'warn' : 'bad')) : '';
        const brkRel = z.brake_linearity != null ? z.brake_linearity.toFixed(2) : '—';
        const brkRelClass = z.brake_linearity != null ? (z.brake_linearity >= 0.8 ? 'good' : (z.brake_linearity >= 0.5 ? 'warn' : 'bad')) : '';
        const brkDur = z.brake_duration_s != null ? z.brake_duration_s.toFixed(2) + 's' : '—';
        const thrOn = z.thr_on != null ? z.thr_on.toFixed(2) + 's' : '—';
        const thrLag = z.thr_lag != null ? z.thr_lag.toFixed(2) + 's' : '—';
        const thrLagClass = z.thr_lag != null && z.thr_lag > 0.5 ? 'warn' : '';
        const apexStd = z.apex_std_mph != null ? '±' + z.apex_std_mph.toFixed(1) : '—';
        const apexStdClass = z.apex_std_mph != null && z.apex_std_mph > 5 ? 'bad' : (z.apex_std_mph != null && z.apex_std_mph > 2 ? 'warn' : '');
        return `<tr>
            <td>${z.pct.toFixed(1)}%</td>
            <td>${escHtml(z.turn_name)}</td>
            <td class="num">${Math.round(z.entry_mph)} mph</td>
            <td class="num">${Math.round(z.min_mph)} mph</td>
            <td class="num ${apexStdClass}">${apexStd}</td>
            <td class="num ${absClass}">${z.abs}</td>
            <td class="num ${t2pClass}">${t2p}</td>
            <td class="num ${brkRelClass}">${brkRel}</td>
            <td class="num">${brkDur}</td>
            <td class="num">${thrOn}</td>
            <td class="num ${thrLagClass}">${thrLag}</td>
            <td>${z.notes ? z.notes.join(', ') : ''}</td>
        </tr>`;
    }).join('');

    document.getElementById('braking-table').innerHTML = `<table><thead>${headers}</thead><tbody>${rows}</tbody></table>`;
}

function renderVarianceTable() {
    const cv = DATA.corner_variance;
    if (!cv.length) {
        document.getElementById('variance-table').innerHTML = '<p style="color:var(--text-secondary);">Not enough laps for variance analysis.</p>';
        return;
    }

    // Compute exit priority: corners before longer straights are more valuable
    // Sort by weighted score: time_loss × exit_weight
    const zones = DATA.braking_zones;
    const trackLength = DATA.track_length_m || 3000;
    const cvWithPriority = cv.map(c => {
        // Find distance to next braking zone (proxy for straight length after this corner)
        const zonePcts = zones.map(z => z.pct).sort((a, b) => a - b);
        let nextZonePct = 100;  // wrap to start
        for (const zp of zonePcts) {
            if (zp > c.pct + 5) { nextZonePct = zp; break; }
        }
        const straightPct = nextZonePct - c.pct;
        const straightM = (straightPct / 100) * trackLength;
        // Exit weight: longer straight = more valuable (normalized 1-3x multiplier)
        const exitWeight = 1 + Math.min(2, straightM / 500);
        const score = c.loss * exitWeight;
        return { ...c, exitWeight: exitWeight, score: score, straightM: Math.round(straightM) };
    });

    // Sort by score (highest first)
    cvWithPriority.sort((a, b) => b.score - a.score);

    const headers = '<tr><th>Zone</th><th>Turn</th><th class="num">Avg</th><th class="num">Best</th><th class="num">Loss</th><th>Priority</th></tr>';
    const rows = cvWithPriority.map(c => {
        const lossClass = c.loss > 0.5 ? 'bad' : (c.loss > 0.3 ? 'warn' : '');
        let priority;
        if (c.score > 0.8) priority = '<strong class="bad">HIGH</strong>';
        else if (c.score > 0.4) priority = '<span class="warn">Medium</span>';
        else priority = '<span style="color:var(--text-secondary)">Low</span>';
        return `<tr>
            <td>${c.pct.toFixed(1)}%</td>
            <td>${escHtml(c.turn_name)}</td>
            <td class="num">${c.avg.toFixed(2)}s</td>
            <td class="num">${c.best.toFixed(2)}s</td>
            <td class="num ${lossClass}">${c.loss.toFixed(2)}s</td>
            <td>${priority}</td>
        </tr>`;
    }).join('');

    const total = cv.reduce((sum, c) => sum + c.loss, 0);
    document.getElementById('variance-table').innerHTML =
        `<table><thead>${headers}</thead><tbody>${rows}</tbody></table>
         <div style="margin-top:8px;font-size:11px;color:var(--text-secondary)">Total recoverable: <span class="info">${total.toFixed(2)}s</span></div>`;
}

function renderLapTable() {
    const laps = DATA.lap_results;
    if (!laps.length) return;

    const bestLap = DATA.best_lap;
    const headers = '<tr><th>Lap</th><th class="num">Time</th><th class="num">ABS</th><th class="num">Max Speed</th></tr>';
    const rows = laps.map(l => {
        const isBest = l.lap === bestLap;
        const time = l.time > 0 ? `${Math.floor(l.time/60)}:${(l.time%60).toFixed(1).padStart(4,'0')}` : '—';
        return `<tr${isBest ? ' style="background:var(--bg-surface-raised)"' : ''}>
            <td>${l.lap}${isBest ? ' ★' : ''}</td>
            <td class="num${isBest ? ' good' : ''}">${time}</td>
            <td class="num">${l.abs}</td>
            <td class="num">${Math.round(l.max_speed_mph)} mph</td>
        </tr>`;
    }).join('');

    document.getElementById('lap-table').innerHTML = `<table><thead>${headers}</thead><tbody>${rows}</tbody></table>`;
}

function renderBrakeRelease() {
    const zones = DATA.braking_zones;
    const grid = document.getElementById('brake-release-grid');
    if (!grid || !zones.length) return;

    // Get exit metrics for selected lap
    const lapKey = String(selectedLap);
    const exitMetrics = DATA.exit_metrics_all && DATA.exit_metrics_all[lapKey]
        ? DATA.exit_metrics_all[lapKey]
        : zones.map(z => ({ brake_release_curve: z.brake_release_curve || [], brake_linearity: z.brake_linearity }));

    // Get comparison lap exit metrics if active
    let cmpMetrics = null;
    if (compareLap !== null) {
        const cmpKey = String(compareLap);
        cmpMetrics = DATA.exit_metrics_all && DATA.exit_metrics_all[cmpKey]
            ? DATA.exit_metrics_all[cmpKey] : null;
    }

    // Filter zones that have curve data for the selected lap
    const withCurves = [];
    for (let i = 0; i < zones.length; i++) {
        const em = exitMetrics[i];
        if (em && em.brake_release_curve && em.brake_release_curve.length > 0) {
            withCurves.push({ zone: zones[i], em: em, idx: i });
        }
    }

    if (!withCurves.length) {
        document.getElementById('brake-release-section').style.display = 'none';
        return;
    }
    document.getElementById('brake-release-section').style.display = '';

    const w = 120, h = 50;

    grid.innerHTML = withCurves.map(({ zone, em, idx }) => {
        const curve = em.brake_release_curve;
        const score = em.brake_linearity;
        const turnName = zone.turn_name || `${zone.pct.toFixed(0)}%`;

        // Score color
        let scoreColor = 'var(--accent-green)';
        let scoreLabel = 'LINEAR';
        if (score < 0.5) { scoreColor = 'var(--accent-red)'; scoreLabel = 'STEP'; }
        else if (score < 0.8) { scoreColor = 'var(--accent-amber)'; scoreLabel = 'MIXED'; }

        // Build primary SVG path
        const points = curve.map((v, i) => {
            const x = (i / (curve.length - 1)) * w;
            const y = h - (v * h);
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');

        // Reference line (perfect linear)
        const refPoints = `0,0 ${w},${h}`;

        // Comparison curve (dashed, same color but dimmed)
        let cmpSvg = '';
        if (cmpMetrics && cmpMetrics[idx] && cmpMetrics[idx].brake_release_curve && cmpMetrics[idx].brake_release_curve.length > 0) {
            const cmpCurve = cmpMetrics[idx].brake_release_curve;
            const cmpPoints = cmpCurve.map((v, i) => {
                const x = (i / (cmpCurve.length - 1)) * w;
                const y = h - (v * h);
                return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(' ');
            const cmpScore = cmpMetrics[idx].brake_linearity;

            // Use same color as primary but at 50% opacity
            const cmpColor = scoreColor.replace('var(--accent-', '').replace(')', '');
            let cmpHex = '#ffab0080';  // default amber
            if (score >= 0.8) cmpHex = '#00e67680';
            else if (score < 0.5) cmpHex = '#ff174480';

            cmpSvg = `<polyline points="${cmpPoints}" fill="none" stroke="${cmpHex}" stroke-width="1.5" stroke-dasharray="4,3" stroke-linecap="round"/>`;

            // Show delta score
            if (cmpScore !== null && score !== null) {
                const delta = score - cmpScore;
                const deltaStr = delta >= 0 ? `+${delta.toFixed(2)}` : delta.toFixed(2);
                const deltaColor = delta >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
                scoreLabel += ` <span style="color:${deltaColor};font-size:9px;">(${deltaStr})</span>`;
            }
        }

        return `<div class="release-card">
            <div class="release-card-title">${escHtml(turnName)}</div>
            <svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
                <polyline points="${refPoints}" fill="none" stroke="#ffffff15" stroke-width="1" stroke-dasharray="3,3"/>
                ${cmpSvg}
                <polyline points="${points}" fill="none" stroke="${scoreColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div class="release-card-score" style="color:${scoreColor}">${score !== null ? score.toFixed(2) : '—'}</div>
            <div class="release-card-label">${scoreLabel}</div>
        </div>`;
    }).join('');
}

// ─── Track Map (Leaflet) ─────────────────────────────────────────────────
function initMap() {
    const trace = getSelectedTrace();
    if (!trace.length) {
        document.getElementById('track-map').innerHTML = '<p style="padding:20px;color:var(--text-secondary);">No GPS data available.</p>';
        return;
    }

    // Rotate coordinates to match iRacing overhead view
    const rotatedTrace = rotateTrace(trace, mapRotation);
    const rotatedBraking = DATA.braking_zones.map(z => {
        if (z.lat && z.lon) {
            const [rlat, rlon] = rotatePoint(z.lat, z.lon, trace, mapRotation);
            return { ...z, rlat, rlon };
        }
        return z;
    });

    // Calculate bounds from rotated coords
    const lats = rotatedTrace.map(p => p.rlat);
    const lons = rotatedTrace.map(p => p.rlon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);

    const bounds = L.latLngBounds([minLat, minLon], [maxLat, maxLon]);
    const center = bounds.getCenter();

    map = L.map('track-map', {
        center: center,
        zoom: 14,
        zoomControl: false,
        attributionControl: false,
        dragging: true,
        scrollWheelZoom: true,
        zoomSnap: 0.25,
        zoomDelta: 0.5,
    });

    // Expose globally so view-switcher can invalidateSize when Detailed becomes visible
    window._tenthsMap = map;
    window._tenthsMapBounds = bounds;

    map.getContainer().style.background = '#000';

    // Track name watermark
    const watermark = document.getElementById('map-watermark');
    if (watermark) watermark.textContent = DATA.track;

    // Zoom buttons
    document.getElementById('zoom-in').addEventListener('click', () => map.zoomIn());
    document.getElementById('zoom-out').addEventListener('click', () => map.zoomOut());

    drawTrackLine(rotatedTrace);

    // Cursor marker
    cursor = L.circleMarker([rotatedTrace[0].rlat, rotatedTrace[0].rlon], {
        radius: 7,
        color: '#ffffff',
        fillColor: '#ffffff',
        fillOpacity: 1,
        weight: 2,
        opacity: 0,
    }).addTo(map);

    // Corner labels + brake markers
    rotatedBraking.forEach(z => {
        if (z.rlat && z.rlon) {
            L.circleMarker([z.rlat, z.rlon], {
                radius: 6,
                color: '#ff1744',
                fillColor: '#ff1744',
                fillOpacity: 0.9,
                weight: 2,
            }).addTo(map);

            const label = L.tooltip({
                permanent: true,
                direction: 'top',
                className: 'corner-label',
                offset: [0, -12],
            });
            label.setContent(z.turn_name);
            label.setLatLng([z.rlat, z.rlon]);
            label.addTo(map);
        }
    });

    // Direction arrow
    if (rotatedTrace.length > 10) {
        const startPt = rotatedTrace[0];
        const nextPt = rotatedTrace[10];  // 5% ahead for clear direction
        // Leaflet renders lat as Y (up) and lon as X (right)
        // atan2(dx, dy) gives angle from north, clockwise positive
        const dx = nextPt.rlon - startPt.rlon;
        const dy = nextPt.rlat - startPt.rlat;
        const angleDeg = Math.atan2(dx, dy) * (180 / Math.PI);

        const arrowPt = rotatedTrace[5];
        const arrowIcon = L.divIcon({
            className: 'direction-arrow',
            html: `<svg width="28" height="28" viewBox="0 0 24 24" style="transform: rotate(${angleDeg}deg);">
                <polygon points="12,2 20,18 12,14 4,18" fill="#ffffff" opacity="0.95"/>
            </svg>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });
        L.marker([arrowPt.rlat, arrowPt.rlon], { icon: arrowIcon, interactive: false }).addTo(map);

        // S/F marker
        L.circleMarker([startPt.rlat, startPt.rlon], {
            radius: 5, color: '#ffffff', fillColor: '#ffffff', fillOpacity: 0.8, weight: 2,
        }).addTo(map);
        const sfLabel = L.tooltip({ permanent: true, direction: 'bottom', className: 'sf-label', offset: [0, 8] });
        sfLabel.setContent('S/F');
        sfLabel.setLatLng([startPt.rlat, startPt.rlon]);
        sfLabel.addTo(map);
    }

    // Fit bounds
    setTimeout(() => {
        map.invalidateSize();
        map.fitBounds(bounds, { padding: [30, 30], maxZoom: 18, animate: false });
    }, 50);

    // Mouse events — use rotated coords for lookup
    map.on('mousemove', (e) => onMapHoverRotated(e, rotatedTrace));
    map.on('mouseout', () => { hoverPct = null; });

    // Store rotated trace for hover sync
    window.__rotatedTrace = rotatedTrace;
}

// Rotate all trace points around center by given degrees clockwise
function rotateTrace(trace, deg) {
    const lats = trace.map(p => p.lat);
    const lons = trace.map(p => p.lon);
    const cLat = (Math.min(...lats) + Math.max(...lats)) / 2;
    const cLon = (Math.min(...lons) + Math.max(...lons)) / 2;
    const rad = -deg * Math.PI / 180;  // negative for clockwise

    return trace.map(p => {
        const dLat = p.lat - cLat;
        const dLon = p.lon - cLon;
        const rlat = cLat + dLat * Math.cos(rad) - dLon * Math.sin(rad);
        const rlon = cLon + dLat * Math.sin(rad) + dLon * Math.cos(rad);
        return { ...p, rlat, rlon };
    });
}

function rotatePoint(lat, lon, trace, deg) {
    const lats = trace.map(p => p.lat);
    const lons = trace.map(p => p.lon);
    const cLat = (Math.min(...lats) + Math.max(...lats)) / 2;
    const cLon = (Math.min(...lons) + Math.max(...lons)) / 2;
    const rad = -deg * Math.PI / 180;
    const dLat = lat - cLat;
    const dLon = lon - cLon;
    return [
        cLat + dLat * Math.cos(rad) - dLon * Math.sin(rad),
        cLon + dLat * Math.sin(rad) + dLon * Math.cos(rad),
    ];
}

function onMapHoverRotated(e, rotatedTrace) {
    if (!rotatedTrace.length) return;
    const latlng = e.latlng;
    let minDist = Infinity, closestIdx = 0;
    for (let i = 0; i < rotatedTrace.length; i++) {
        const dx = rotatedTrace[i].rlat - latlng.lat;
        const dy = rotatedTrace[i].rlon - latlng.lng;
        const d = dx*dx + dy*dy;
        if (d < minDist) { minDist = d; closestIdx = i; }
    }
    hoverPct = rotatedTrace[closestIdx].pct;
}

function drawTrackLine(rotatedTrace) {
    const trace = rotatedTrace || window.__rotatedTrace || DATA.gps_trace;

    // Remove existing hotline if any
    if (hotline) { map.removeLayer(hotline); }

    // Build coords with color value
    const coords = trace.map(p => {
        const lat = p.rlat || p.lat;
        const lon = p.rlon || p.lon;
        let val;
        if (mapMode === 'speed') {
            const speeds = trace.map(t => t.speed_mph);
            const minSpd = Math.min(...speeds), maxSpd = Math.max(...speeds);
            val = maxSpd > minSpd ? (p.speed_mph - minSpd) / (maxSpd - minSpd) : 0.5;
        } else {
            val = (p.brake || 0) / 100;
        }
        return [lat, lon, val];
    });

    // Draw with manual color interpolation using polyline segments
    const segments = [];
    for (let i = 0; i < coords.length - 1; i++) {
        const val = coords[i][2];
        const color = mapMode === 'speed' ? speedColor(val) : brakeColor(val);
        const seg = L.polyline(
            [[coords[i][0], coords[i][1]], [coords[i+1][0], coords[i+1][1]]],
            { color: color, weight: 6, opacity: 0.95 }
        );
        segments.push(seg);
    }
    // Close the loop
    if (coords.length > 2) {
        const lastVal = coords[coords.length-1][2];
        const lastColor = mapMode === 'speed' ? speedColor(lastVal) : brakeColor(lastVal);
        segments.push(L.polyline(
            [[coords[coords.length-1][0], coords[coords.length-1][1]], [coords[0][0], coords[0][1]]],
            { color: lastColor, weight: 6, opacity: 0.95 }
        ));
    }

    hotline = L.layerGroup(segments).addTo(map);
}

function speedColor(val) {
    // 0 (slow/braking) = red, 0.5 (coast) = amber, 1 (fast) = green
    if (val < 0.5) {
        const t = val / 0.5;
        return lerpColor('#ff1744', '#ffab00', t);
    } else {
        const t = (val - 0.5) / 0.5;
        return lerpColor('#ffab00', '#00e676', t);
    }
}

function brakeColor(val) {
    // 0 (no brake) = dark grey, 1 (full brake) = bright red
    if (val < 0.05) return '#333333';
    return lerpColor('#555555', '#ff1744', Math.min(val * 1.2, 1));
}

function lerpColor(a, b, t) {
    const ah = parseInt(a.slice(1), 16);
    const bh = parseInt(b.slice(1), 16);
    const ar = (ah >> 16) & 0xff, ag = (ah >> 8) & 0xff, ab = ah & 0xff;
    const br = (bh >> 16) & 0xff, bg = (bh >> 8) & 0xff, bb = bh & 0xff;
    const rr = Math.round(ar + (br - ar) * t);
    const rg = Math.round(ag + (bg - ag) * t);
    const rb = Math.round(ab + (bb - ab) * t);
    return `#${((rr << 16) | (rg << 8) | rb).toString(16).padStart(6, '0')}`;
}

// ─── Telemetry Charts (Stacked Panels — MoTeC style) ────────────────────
let charts = [];

function initChart() {
    const trace = getSelectedTrace();
    if (!trace.length) return;

    const labels = trace.map(p => p.pct.toFixed(1));
    const maxSpeed = Math.max(...trace.map(p => p.speed_mph));

    // Vertical line plugin (crosshair synced across all panels)
    const crosshairPlugin = {
        id: 'crosshair',
        afterDraw: (chart) => {
            if (hoverPct === null) return;
            const traceData = getSelectedTrace();
            let idx = 0, minDiff = Infinity;
            for (let i = 0; i < traceData.length; i++) {
                const diff = Math.abs(traceData[i].pct - hoverPct);
                if (diff < minDiff) { minDiff = diff; idx = i; }
            }
            const meta = chart.getDatasetMeta(0);
            if (!meta.data[idx]) return;
            const x = meta.data[idx].x;
            const ctx = chart.ctx;
            const yAxis = chart.scales.y;
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(x, yAxis.top);
            ctx.lineTo(x, yAxis.bottom);
            ctx.lineWidth = 1;
            ctx.strokeStyle = '#ffffff60';
            ctx.stroke();
            ctx.restore();
        }
    };

    // Shared options factory
    function makeOpts(showXAxis, max, tickSuffix) {
        // For percentage axes (0-100), show every 25%
        // For speed, show every 10 mph
        const stepSize = max === 100 ? 25 : 10;
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
                x: {
                    display: showXAxis,
                    ticks: { color: '#8890a4', font: { size: 8 }, maxTicksLimit: 20 },
                    grid: { color: '#1a1d2b', drawBorder: false },
                    ...(showXAxis ? { title: { display: true, text: 'Lap Distance %', color: '#8890a4', font: { size: 9 } } } : {}),
                },
                y: {
                    display: true,
                    position: 'right',
                    min: 0,
                    max: max,
                    ticks: {
                        color: '#8890a4',
                        font: { size: 8 },
                        stepSize: stepSize,
                        callback: (v) => v + tickSuffix,
                    },
                    grid: { color: '#1a1d2b', drawBorder: false },
                }
            },
            onHover: (event, elements) => {
                if (elements.length > 0) {
                    hoverPct = getSelectedTrace()[elements[0].index].pct;
                }
            }
        };
    }

    // Comparison trace (if active)
    const cmpTrace = getCompareTrace();
    const cmpStyle = { borderDash: [6, 4], borderWidth: 1.2, pointRadius: 0, fill: false };

    // Brake + Throttle panel
    const btDatasets = [
        {
            data: trace.map(p => p.throttle || 0),
            borderColor: '#00e676',
            backgroundColor: '#00e67618',
            fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0, order: 2,
        },
        {
            data: trace.map(p => p.brake || 0),
            borderColor: '#ff1744',
            backgroundColor: '#ff174430',
            fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0, order: 1,
        },
    ];
    if (cmpTrace) {
        btDatasets.push({
            data: cmpTrace.map(p => p.throttle || 0),
            borderColor: '#00e67680', ...cmpStyle, tension: 0, order: 4,
        });
        btDatasets.push({
            data: cmpTrace.map(p => p.brake || 0),
            borderColor: '#ff174480', ...cmpStyle, tension: 0, order: 3,
        });
    }
    charts.push(new Chart(document.getElementById('chart-brake-throttle').getContext('2d'), {
        type: 'line', plugins: [crosshairPlugin],
        data: { labels: labels, datasets: btDatasets },
        options: makeOpts(false, 100, '%'),
    }));

    // Speed panel
    const speedDatasets = [{
        data: trace.map(p => p.speed_mph),
        borderColor: '#ffab00', backgroundColor: '#ffab0015',
        fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0.15,
    }];
    if (cmpTrace) {
        speedDatasets.push({
            data: cmpTrace.map(p => p.speed_mph),
            borderColor: '#ffab0080', ...cmpStyle, tension: 0.15,
        });
    }
    charts.push(new Chart(document.getElementById('chart-speed').getContext('2d'), {
        type: 'line', plugins: [crosshairPlugin],
        data: { labels: labels, datasets: speedDatasets },
        options: makeOpts(false, Math.ceil(maxSpeed / 10) * 10, ''),
    }));

    // Speed Delta panel (only when comparing)
    if (cmpTrace) {
        const deltaData = trace.map((p, i) => {
            const cmpSpeed = cmpTrace[i] ? cmpTrace[i].speed_mph : p.speed_mph;
            return p.speed_mph - cmpSpeed;
        });
        const maxDelta = Math.max(Math.abs(Math.min(...deltaData)), Math.abs(Math.max(...deltaData)));
        const deltaMax = Math.ceil(maxDelta / 5) * 5 || 10;

        const deltaOpts = makeOpts(false, deltaMax, '');
        deltaOpts.scales.y.min = -deltaMax;
        deltaOpts.scales.y.ticks.stepSize = deltaMax > 20 ? 10 : 5;

        // Custom fill: green above zero, red below
        charts.push(new Chart(document.getElementById('chart-delta').getContext('2d'), {
            type: 'line', plugins: [crosshairPlugin],
            data: {
                labels: labels,
                datasets: [{
                    data: deltaData,
                    borderColor: '#ffffff',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.15,
                    fill: {
                        target: { value: 0 },
                        above: '#00e67630',
                        below: '#ff174430',
                    },
                    segment: {
                        borderColor: ctx => ctx.p0.parsed.y >= 0 ? '#00e676' : '#ff1744',
                    },
                }]
            },
            options: deltaOpts,
        }));
    }

    // Steering panel
    const steeringData = trace.map(p => p.steering || 0);
    const maxSteer = Math.max(Math.abs(Math.min(...steeringData)), Math.abs(Math.max(...steeringData)));
    const steerMax = Math.ceil(maxSteer / 45) * 45 || 45;

    const steerOpts = makeOpts(true, steerMax, '°');
    steerOpts.scales.y.min = -steerMax;
    steerOpts.scales.y.ticks.stepSize = steerMax > 90 ? 45 : 30;

    const steerDatasets = [{
        data: steeringData,
        borderColor: '#448aff', backgroundColor: '#448aff15',
        fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0.15,
    }];
    if (cmpTrace) {
        steerDatasets.push({
            data: cmpTrace.map(p => p.steering || 0),
            borderColor: '#448aff80', ...cmpStyle, tension: 0.15,
        });
    }
    charts.push(new Chart(document.getElementById('chart-steering').getContext('2d'), {
        type: 'line', plugins: [crosshairPlugin],
        data: { labels: labels, datasets: steerDatasets },
        options: steerOpts,
    }));
}

// ─── Toggle ──────────────────────────────────────────────────────────────
function initToggle() {
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            mapMode = btn.dataset.mode;
            drawTrackLine(window.__rotatedTrace);
            if (showBrakePoints) renderBrakePoints();
        });
    });

    // Rotation controls
    document.querySelectorAll('.rotate-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const dir = parseInt(btn.dataset.dir);
            mapRotation = (mapRotation + dir * 15 + 360) % 360;
            document.getElementById('rotate-label').textContent = mapRotation + '°';
            try { localStorage.setItem('tenths_rotation_' + DATA.track, mapRotation); } catch(e) {}
            rebuildMap();
        });
    });

    // Brake Points toggle
    const bpBtn = document.getElementById('brake-points-toggle');
    if (bpBtn) {
        bpBtn.addEventListener('click', () => {
            showBrakePoints = !showBrakePoints;
            bpBtn.classList.toggle('active', showBrakePoints);
            document.getElementById('brake-points-legend').style.display = showBrakePoints ? 'flex' : 'none';
            renderBrakePoints();
        });
    }
}

function rebuildMap() {
    // Clear all layers except tile layer
    map.eachLayer(l => map.removeLayer(l));
    hotline = null;

    const trace = getSelectedTrace();
    const rotatedTrace = rotateTrace(trace, mapRotation);
    const rotatedBraking = DATA.braking_zones.map(z => {
        if (z.lat && z.lon) {
            const [rlat, rlon] = rotatePoint(z.lat, z.lon, trace, mapRotation);
            return { ...z, rlat, rlon };
        }
        return z;
    });

    window.__rotatedTrace = rotatedTrace;

    // Recalculate bounds
    const lats = rotatedTrace.map(p => p.rlat);
    const lons = rotatedTrace.map(p => p.rlon);
    const bounds = L.latLngBounds([Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]);

    drawTrackLine(rotatedTrace);

    // Cursor
    cursor = L.circleMarker([rotatedTrace[0].rlat, rotatedTrace[0].rlon], {
        radius: 7, color: '#ffffff', fillColor: '#ffffff', fillOpacity: 1, weight: 2, opacity: 0,
    }).addTo(map);

    // Corner labels
    rotatedBraking.forEach(z => {
        if (z.rlat && z.rlon) {
            L.circleMarker([z.rlat, z.rlon], {
                radius: 6, color: '#ff1744', fillColor: '#ff1744', fillOpacity: 0.9, weight: 2,
            }).addTo(map);
            const label = L.tooltip({ permanent: true, direction: 'top', className: 'corner-label', offset: [0, -12] });
            label.setContent(z.turn_name);
            label.setLatLng([z.rlat, z.rlon]);
            label.addTo(map);
        }
    });

    // Direction arrow
    if (rotatedTrace.length > 10) {
        const startPt = rotatedTrace[0];
        const nextPt = rotatedTrace[10];
        const dx = nextPt.rlon - startPt.rlon;
        const dy = nextPt.rlat - startPt.rlat;
        const angleDeg = Math.atan2(dx, dy) * (180 / Math.PI);
        const arrowPt = rotatedTrace[5];
        const arrowIcon = L.divIcon({
            className: 'direction-arrow',
            html: `<svg width="28" height="28" viewBox="0 0 24 24" style="transform: rotate(${angleDeg}deg);"><polygon points="12,2 20,18 12,14 4,18" fill="#ffffff" opacity="0.95"/></svg>`,
            iconSize: [28, 28], iconAnchor: [14, 14],
        });
        L.marker([arrowPt.rlat, arrowPt.rlon], { icon: arrowIcon, interactive: false }).addTo(map);
        L.circleMarker([startPt.rlat, startPt.rlon], { radius: 5, color: '#ffffff', fillColor: '#ffffff', fillOpacity: 0.8, weight: 2 }).addTo(map);
        const sfLabel = L.tooltip({ permanent: true, direction: 'bottom', className: 'sf-label', offset: [0, 8] });
        sfLabel.setContent('S/F');
        sfLabel.setLatLng([startPt.rlat, startPt.rlon]);
        sfLabel.addTo(map);
    }

    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 18, animate: true });

    // Re-render brake points if active
    if (showBrakePoints) renderBrakePoints();
}

// ─── Brake Points Overlay ────────────────────────────────────────────────
function renderBrakePoints() {
    // Remove existing layer
    if (brakePointsLayer) {
        map.removeLayer(brakePointsLayer);
        brakePointsLayer = null;
    }

    if (!showBrakePoints || !DATA.per_lap_brake_points || !DATA.per_lap_brake_points.length) return;

    // Create a custom pane with higher z-index for brake points
    if (!map.getPane('brakePointsPane')) {
        map.createPane('brakePointsPane');
        map.getPane('brakePointsPane').style.zIndex = 650;  // above default marker pane (600)
    }

    const trace = DATA.gps_trace;
    const markers = [];
    const totalLaps = DATA.valid_laps || 1;

    DATA.per_lap_brake_points.forEach(zone => {
        if (!zone.entries || !zone.entries.length) return;

        // Find min/max lap numbers for color interpolation
        const lapNums = zone.entries.map(e => e.lap);
        const minLap = Math.min(...lapNums);
        const maxLap = Math.max(...lapNums);
        const lapRange = maxLap - minLap || 1;

        zone.entries.forEach(entry => {
            // Rotate the point to match current map rotation
            const [rlat, rlon] = rotatePoint(entry.lat, entry.lon, trace, mapRotation);

            // Color gradient: early laps = blue, late laps = amber
            const t = (entry.lap - minLap) / lapRange;
            const color = lerpColor('#448aff', '#ffab00', t);

            const marker = L.circleMarker([rlat, rlon], {
                radius: 5,
                color: '#000000',
                fillColor: color,
                fillOpacity: 0.9,
                weight: 1.5,
                pane: 'brakePointsPane',
            }).bindTooltip(
                `Lap ${entry.lap} — ${entry.entry_pct.toFixed(1)}% — ${Math.round(entry.speed_mph)} mph`,
                { direction: 'top', className: 'corner-label', offset: [0, -6] }
            );
            markers.push(marker);
        });

        // Add spread label at zone center (use average position)
        if (zone.spread_meters > 0) {
            const avgLat = zone.entries.reduce((s, e) => s + e.lat, 0) / zone.entries.length;
            const avgLon = zone.entries.reduce((s, e) => s + e.lon, 0) / zone.entries.length;
            const [rlat, rlon] = rotatePoint(avgLat, avgLon, trace, mapRotation);

            const spreadColor = zone.spread_meters > 10 ? '#ff1744' : (zone.spread_meters > 5 ? '#ffab00' : '#00e676');
            const spreadLabel = L.tooltip({
                permanent: true,
                direction: 'bottom',
                className: 'spread-label',
                offset: [0, 12],
            });
            spreadLabel.setContent(`±${zone.spread_meters.toFixed(0)}m`);
            spreadLabel.setLatLng([rlat, rlon]);
            markers.push(spreadLabel);
        }
    });

    brakePointsLayer = L.layerGroup(markers).addTo(map);
    // Ensure brake points render on top of the track line
    brakePointsLayer.eachLayer(l => { if (l.bringToFront) l.bringToFront(); });
}

// ─── Hover Sync Loop (rAF) ──────────────────────────────────────────────
function startHoverLoop() {
    let lastPct = null;
    const info = document.getElementById('crosshair-info');

    function tick() {
        if (hoverPct !== lastPct) {
            lastPct = hoverPct;

            if (hoverPct !== null && getSelectedTrace().length > 0) {
                // Find the trace point closest to hoverPct
                const selTrace = getSelectedTrace();
                let closest = selTrace[0];
                let minDiff = Infinity;
                for (const p of selTrace) {
                    const diff = Math.abs(p.pct - hoverPct);
                    if (diff < minDiff) { minDiff = diff; closest = p; }
                }

                // Update map cursor
                if (cursor && map && window.__rotatedTrace) {
                    const rt = window.__rotatedTrace;
                    let closestRt = rt[0];
                    let minD = Infinity;
                    for (const p of rt) {
                        const diff = Math.abs(p.pct - hoverPct);
                        if (diff < minD) { minD = diff; closestRt = p; }
                    }
                    cursor.setLatLng([closestRt.rlat, closestRt.rlon]);
                    cursor.setStyle({ opacity: 1, fillOpacity: 1 });
                }

                // Update crosshair on all charts
                charts.forEach(c => c.draw());

                // Update info bar
                info.classList.add('visible');
                info.innerHTML = `${hoverPct.toFixed(1)}% — ${Math.round(closest.speed_mph)} mph — Brake: ${Math.round(closest.brake || 0)}% — Throttle: ${Math.round(closest.throttle || 0)}%`;

            } else {
                if (cursor) cursor.setStyle({ opacity: 0, fillOpacity: 0 });
                info.classList.remove('visible');
                charts.forEach(c => c.draw());
            }
        }
        requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}

// ─── Helpers ─────────────────────────────────────────────────────────────
function escHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}
'''


def _get_summary_css():
    """CSS for the Summary View — VR-readable, no external dependencies."""
    return '''
/* ─── View Switching ──────────────────────────────────────────────────────── */
.view-switcher {
    display: flex;
    gap: 4px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px;
}
.view-tab {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 18px;
    font-weight: 500;
    padding: 10px 24px;
    min-width: 44px;
    min-height: 44px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    background: transparent;
    color: var(--text-secondary);
    transition: all 0.15s;
}
.view-tab.active {
    background: var(--bg-surface-raised);
    color: var(--text-primary);
}
.view-tab:hover:not(.active) {
    color: var(--text-primary);
}
.view-tab:focus-visible {
    outline: 2px solid var(--accent-blue);
    outline-offset: 2px;
}
.view-panel { display: none; }
.view-panel.active { display: block; }

/* ─── Summary View ────────────────────────────────────────────────────────── */
.summary-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px;
}
.hero-row {
    display: flex;
    justify-content: center;
    gap: 48px;
    flex-wrap: wrap;
    margin-bottom: 32px;
}
.hero-stat {
    text-align: center;
}
.hero-value {
    font-family: 'Orbitron', system-ui, sans-serif;
    font-size: 48px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
}
.hero-value.green { color: var(--accent-green); }
.hero-value.red { color: var(--accent-red); }
.hero-value.muted { color: var(--text-secondary); font-size: 28px; }
.hero-label {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 12px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 4px;
}
.pb-badge {
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 16px;
    font-weight: 700;
    color: var(--accent-green);
    background: #00e67615;
    border: 1px solid #00e67640;
    border-radius: 4px;
    padding: 2px 8px;
    margin-left: 8px;
}
.race-info-summary {
    font-family: 'JetBrains Mono', monospace;
    font-size: 16px;
    color: var(--text-secondary);
    margin-top: 4px;
}

/* Next Race Focus */
.next-focus {
    background: var(--bg-surface);
    border: 2px solid var(--accent-blue);
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 24px;
    cursor: pointer;
    transition: border-color 0.15s;
}
.next-focus:hover {
    border-color: var(--accent-green);
}
.next-focus-header {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent-blue);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
}
.next-focus-turn {
    font-family: 'JetBrains Mono', monospace;
    font-size: 24px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 4px;
}
.next-focus-loss {
    font-family: 'Orbitron', system-ui, sans-serif;
    font-size: 20px;
    font-weight: 700;
    color: var(--accent-red);
    margin-bottom: 8px;
}
.next-focus-sentence {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 20px;
    font-weight: 400;
    color: var(--text-primary);
    line-height: 1.5;
}
.next-focus-hidden { display: none; }

/* Focus Cards */
.focus-cards {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

/* Summary two-column layout */
.summary-body {
    display: flex;
    gap: 24px;
    align-items: flex-start;
}
.summary-left {
    flex: 1;
    min-width: 0;
}
.summary-right {
    flex: 0 0 280px;
    position: sticky;
    top: 80px;
}
#mini-map {
    width: 280px;
    height: 280px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg-surface);
}
@media (max-width: 900px) {
    .summary-body { flex-direction: column-reverse; }
    .summary-right { flex: none; width: 100%; position: static; }
    #mini-map { width: 100%; height: 200px; }
}
.focus-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
}
.focus-card:hover {
    border-color: var(--accent-blue);
    background: var(--bg-surface-raised);
}
.focus-card-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 6px;
}
.focus-card-turn {
    font-family: 'JetBrains Mono', monospace;
    font-size: 24px;
    font-weight: 700;
    color: var(--text-primary);
}
.focus-card-loss {
    font-family: 'Orbitron', system-ui, sans-serif;
    font-size: 20px;
    font-weight: 700;
    color: var(--accent-red);
}
.focus-card-sentence {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 16px;
    font-weight: 400;
    color: var(--text-secondary);
    line-height: 1.4;
}
.focus-card-speed, .next-focus-speed {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 400;
    color: var(--accent-amber);
    margin-left: 8px;
}
.consistent-message {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 18px;
    color: var(--accent-green);
    text-align: center;
    padding: 32px;
}

/* Drill-down highlight */
.highlight-row {
    animation: row-pulse 3s ease-out;
}
@keyframes row-pulse {
    0% { background: var(--accent-blue); }
    100% { background: transparent; }
}
'''


def _get_summary_js():
    """JavaScript for the Summary View — view switching, coaching logic, drill-down."""
    return '''
// ─── View Switching ──────────────────────────────────────────────────────────
(function() {
    const storageKey = 'tenths_view_' + document.title;
    const tabs = document.querySelectorAll('.view-tab');
    const panels = document.querySelectorAll('.view-panel');
    let currentView = 'summary';

    function getStoredView() {
        try { return localStorage.getItem(storageKey) || 'summary'; }
        catch(e) { return 'summary'; }
    }

    function setStoredView(view) {
        try { localStorage.setItem(storageKey, view); }
        catch(e) {}
    }

    function switchView(view) {
        if (view === currentView) return;
        currentView = view;
        tabs.forEach(tab => {
            const isActive = tab.dataset.view === view;
            tab.classList.toggle('active', isActive);
            tab.setAttribute('aria-selected', isActive);
            tab.tabIndex = isActive ? 0 : -1;
        });
        panels.forEach(panel => {
            const isActive = panel.id === view + '-view';
            panel.classList.toggle('active', isActive);
        });
        setStoredView(view);
        window.scrollTo(0, 0);

        // Leaflet can't render in a hidden container — invalidate size when Detailed becomes visible
        if (view === 'detailed' && window._tenthsMap) {
            setTimeout(() => {
                window._tenthsMap.invalidateSize();
                if (window._tenthsMapBounds) {
                    window._tenthsMap.fitBounds(window._tenthsMapBounds, { padding: [30, 30] });
                }
            }, 50);
        }
    }

    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchView(tab.dataset.view));
        tab.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                switchView(tab.dataset.view);
            }
        });
    });

    // Restore saved preference
    const saved = getStoredView();
    if (saved === 'detailed') switchView('detailed');

    // Expose for drill-down
    window.switchToDetailed = function() { switchView('detailed'); };

// ─── Coaching Data Builder ───────────────────────────────────────────────────
    function buildCoachingData() {
        const cv = DATA.corner_variance || [];
        const bz = DATA.braking_zones || [];
        const bp = DATA.per_lap_brake_points || [];

        const qualifying = cv
            .filter(c => c.loss > 0.1)
            .sort((a, b) => b.loss - a.loss)
            .slice(0, 3);

        return qualifying.map(c => {
            const zone = bz.find(z => z.turn_name === c.turn_name);
            const brakePoint = bp.find(p => p.turn_name === c.turn_name);
            return {
                turn_name: c.turn_name || 'Unknown',
                loss: c.loss,
                pct: c.pct || 0,
                brake_linearity: zone?.brake_linearity ?? null,
                apex_std_mph: zone?.apex_std_mph ?? null,
                thr_lag: zone?.thr_lag ?? null,
                spread_meters: brakePoint?.spread_meters ?? null,
                entry_mph: zone?.entry_mph ?? null,
                min_mph: zone?.min_mph ?? null,
            };
        });
    }

// ─── Coaching Sentence Generator ─────────────────────────────────────────────
    function generateCoachingSentence(corner) {
        const turn = corner.turn_name;
        const loss = corner.loss.toFixed(3);

        // Priority order: brake linearity, apex consistency, throttle lag, brake spread
        if (corner.brake_linearity !== null && corner.brake_linearity < 0.6) {
            return truncate(`${turn}: Release brake progressively — losing ${loss}s to stepped release`);
        }
        if (corner.apex_std_mph !== null && corner.apex_std_mph > 4) {
            const std = Math.round(corner.apex_std_mph);
            return truncate(`${turn}: Apex speed varies \\u00b1${std}mph — find a consistent visual reference`);
        }
        if (corner.thr_lag !== null && corner.thr_lag > 0.5) {
            const lag = corner.thr_lag.toFixed(1);
            return truncate(`${turn}: Throttle delayed ${lag}s after apex — commit to exit earlier`);
        }
        if (corner.spread_meters !== null && corner.spread_meters > 15) {
            const spread = Math.round(corner.spread_meters);
            return truncate(`${turn}: Brake reference drifting \\u00b1${spread}m — pick a fixed board marker`);
        }
        // Generic fallback
        return truncate(`${turn}: Losing ${loss}s — review telemetry in Detailed view`);
    }

    function getDiagnosisType(corner) {
        if (corner.brake_linearity !== null && corner.brake_linearity < 0.6) return 'brake_linearity';
        if (corner.apex_std_mph !== null && corner.apex_std_mph > 4) return 'apex_consistency';
        if (corner.thr_lag !== null && corner.thr_lag > 0.5) return 'throttle_lag';
        if (corner.spread_meters !== null && corner.spread_meters > 15) return 'brake_spread';
        return 'generic';
    }

    function truncate(s) {
        return s.length > 120 ? s.slice(0, 117) + '...' : s;
    }

// ─── Hero Numbers Renderer ───────────────────────────────────────────────────
    function renderHeroes() {
        const container = document.getElementById('summary-heroes');
        if (!container) return;

        // Best lap
        const bestTime = DATA.best_time || '—';

        // Total recoverable time
        const cv = DATA.corner_variance || [];
        const totalLoss = cv.reduce((sum, c) => sum + (c.loss || 0), 0);
        const lossStr = totalLoss.toFixed(3) + 's';

        // Progression delta
        const prog = DATA.progression;
        let deltaHtml = '';
        if (prog && prog.delta_vs_previous) {
            const delta = prog.delta_vs_previous.lap_time_s;
            const sign = delta < 0 ? '' : '+';
            const cls = delta < 0 ? 'green' : 'red';
            deltaHtml = `<div class="hero-stat">
                <div class="hero-value ${cls}">${sign}${delta.toFixed(3)}</div>
                <div class="hero-label">vs Previous</div>
            </div>`;
            if (prog.alltime_best && prog.alltime_best.is_new_pb) {
                deltaHtml = `<div class="hero-stat">
                    <div class="hero-value ${cls}">${sign}${delta.toFixed(3)}<span class="pb-badge">New PB</span></div>
                    <div class="hero-label">vs Previous</div>
                </div>`;
            }
        } else {
            deltaHtml = `<div class="hero-stat">
                <div class="hero-value muted">First Session</div>
                <div class="hero-label">vs Previous</div>
            </div>`;
        }

        // Laps + race result
        const laps = DATA.valid_laps || 0;
        let raceHtml = '';
        if (DATA.race_result) {
            const r = DATA.race_result;
            const irColor = r.ir_delta >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            const irSign = r.ir_delta >= 0 ? '+' : '';
            raceHtml = `<div class="race-info-summary">P${r.finish_pos}/${r.entries} <span style="color:${irColor}">iR ${irSign}${r.ir_delta}</span></div>`;
        }

        container.innerHTML = `
            <div class="hero-stat">
                <div class="hero-value">${bestTime}</div>
                <div class="hero-label">Best Lap</div>
                ${raceHtml}
            </div>
            <div class="hero-stat">
                <div class="hero-value red">${lossStr}</div>
                <div class="hero-label">Recoverable</div>
            </div>
            ${deltaHtml}
            <div class="hero-stat">
                <div class="hero-value">${laps}</div>
                <div class="hero-label">Laps</div>
            </div>
        `;
    }

// ─── Next Race Focus Renderer ────────────────────────────────────────────────
    function renderNextFocus(coachingData) {
        const container = document.getElementById('next-focus');
        if (!container) return;

        const cv = DATA.corner_variance || [];
        if (cv.length === 0) {
            container.classList.add('next-focus-hidden');
            return;
        }

        // Find highest-loss corner WITH a specific diagnosis
        let focus = null;
        const allByLoss = [...cv].sort((a, b) => b.loss - a.loss);
        const bz = DATA.braking_zones || [];
        const bp = DATA.per_lap_brake_points || [];

        for (const c of allByLoss) {
            if (c.loss <= 0) continue;
            const zone = bz.find(z => z.turn_name === c.turn_name);
            const brakePoint = bp.find(p => p.turn_name === c.turn_name);
            const corner = {
                turn_name: c.turn_name || 'Unknown',
                loss: c.loss,
                pct: c.pct || 0,
                brake_linearity: zone?.brake_linearity ?? null,
                apex_std_mph: zone?.apex_std_mph ?? null,
                thr_lag: zone?.thr_lag ?? null,
                spread_meters: brakePoint?.spread_meters ?? null,
                entry_mph: zone?.entry_mph ?? null,
                min_mph: zone?.min_mph ?? null,
            };
            const diag = getDiagnosisType(corner);
            if (diag !== 'generic') {
                focus = corner;
                break;
            }
        }

        // Fallback: highest loss corner overall
        if (!focus && allByLoss.length > 0 && allByLoss[0].loss > 0) {
            const c = allByLoss[0];
            const zone = bz.find(z => z.turn_name === c.turn_name);
            const brakePoint = bp.find(p => p.turn_name === c.turn_name);
            focus = {
                turn_name: c.turn_name || 'Unknown',
                loss: c.loss,
                pct: c.pct || 0,
                brake_linearity: zone?.brake_linearity ?? null,
                apex_std_mph: zone?.apex_std_mph ?? null,
                thr_lag: zone?.thr_lag ?? null,
                spread_meters: brakePoint?.spread_meters ?? null,
                entry_mph: zone?.entry_mph ?? null,
                min_mph: zone?.min_mph ?? null,
            };
        }

        // All corners with zero/negative loss
        if (!focus) {
            container.innerHTML = `
                <div class="next-focus-header">Next Race Focus</div>
                <div class="next-focus-sentence">Maintain consistency — no significant time loss detected</div>
            `;
            return;
        }

        const sentence = generateCoachingSentence(focus);
        const diagType = getDiagnosisType(focus);
        const speedCtx = focus.entry_mph && focus.min_mph
            ? `<span class="next-focus-speed">${Math.round(focus.entry_mph)}→${Math.round(focus.min_mph)}mph</span>`
            : '';

        container.innerHTML = `
            <div class="next-focus-header">Next Race Focus</div>
            <div class="next-focus-turn">${focus.turn_name} ${speedCtx}</div>
            <div class="next-focus-loss">${focus.loss.toFixed(3)}s</div>
            <div class="next-focus-sentence">${sentence}</div>
        `;
        container.dataset.turn = focus.turn_name;
        container.dataset.diag = diagType;
        container.addEventListener('click', () => drillDown(focus.turn_name, diagType));
    }

// ─── Focus Cards Renderer ────────────────────────────────────────────────────
    function renderFocusCards(coachingData) {
        const container = document.getElementById('focus-cards');
        if (!container) return;

        if (coachingData.length === 0) {
            container.innerHTML = '<div class="consistent-message">No significant time loss detected — consistent session</div>';
            return;
        }

        // Exclude the Next Race Focus corner from the cards (already shown above)
        const nextFocusEl = document.getElementById('next-focus');
        const nextFocusTurn = nextFocusEl?.dataset?.turn || '';
        const filtered = coachingData.filter(c => c.turn_name !== nextFocusTurn);

        if (filtered.length === 0) return;

        container.innerHTML = filtered.map(corner => {
            const sentence = generateCoachingSentence(corner);
            const diagType = getDiagnosisType(corner);
            const speedCtx = corner.entry_mph && corner.min_mph
                ? `<span class="focus-card-speed">${Math.round(corner.entry_mph)}\u2192${Math.round(corner.min_mph)}mph</span>`
                : '';
            return `
                <div class="focus-card" data-turn="${corner.turn_name}" data-diag="${diagType}">
                    <div class="focus-card-header">
                        <span class="focus-card-turn">${corner.turn_name} ${speedCtx}</span>
                        <span class="focus-card-loss">${corner.loss.toFixed(3)}s</span>
                    </div>
                    <div class="focus-card-sentence">${sentence}</div>
                </div>
            `;
        }).join('');

        // Attach click handlers
        container.querySelectorAll('.focus-card').forEach(card => {
            card.addEventListener('click', () => {
                drillDown(card.dataset.turn, card.dataset.diag);
            });
        });
    }

// ─── Drill-Down Navigation ───────────────────────────────────────────────────
    function drillDown(turnName, diagnosisType) {
        window.switchToDetailed();

        setTimeout(() => {
            let target = null;

            if (diagnosisType === 'brake_linearity') {
                // Try to find the brake release panel for this corner
                const releaseGrid = document.getElementById('brake-release-grid');
                if (releaseGrid) {
                    const panels = releaseGrid.querySelectorAll('.release-card');
                    panels.forEach(p => {
                        if (p.textContent.includes(turnName)) target = p;
                    });
                }
            }

            if (!target) {
                // Find the row in braking zones table
                const tableSection = document.getElementById('braking-zones-table-section');
                if (tableSection) {
                    const rows = tableSection.querySelectorAll('tr');
                    rows.forEach(row => {
                        if (row.textContent.includes(turnName)) target = row;
                    });
                }
            }

            if (!target) {
                // Fallback: scroll to braking zones table top
                target = document.getElementById('braking-zones-table-section');
            }

            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                target.classList.add('highlight-row');
                setTimeout(() => target.classList.remove('highlight-row'), 3000);
            }
        }, 100);
    }

// ─── Mini Track Map Renderer ─────────────────────────────────────────────────
    function renderMiniMap(coachingData) {
        const canvas = document.getElementById('mini-map');
        if (!canvas || !DATA.gps_trace || DATA.gps_trace.length < 10) return;

        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth;
        const h = canvas.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.scale(dpr, dpr);

        // Extract lat/lon from GPS trace
        const points = DATA.gps_trace;
        const lats = points.map(p => p.lat);
        const lons = points.map(p => p.lon);
        const minLat = Math.min(...lats), maxLat = Math.max(...lats);
        const minLon = Math.min(...lons), maxLon = Math.max(...lons);

        // Scale to canvas with padding
        const pad = 30;
        const scaleX = (w - pad * 2) / (maxLon - minLon || 1);
        const scaleY = (h - pad * 2) / (maxLat - minLat || 1);
        const scale = Math.min(scaleX, scaleY);

        const cx = w / 2;
        const cy = h / 2;
        const midLon = (minLon + maxLon) / 2;
        const midLat = (minLat + maxLat) / 2;

        function toX(lon) { return cx + (lon - midLon) * scale; }
        function toY(lat) { return cy - (lat - midLat) * scale; }

        // Draw track outline
        ctx.beginPath();
        ctx.moveTo(toX(points[0].lon), toY(points[0].lat));
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(toX(points[i].lon), toY(points[i].lat));
        }
        ctx.strokeStyle = '#2a2d3a';
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.stroke();

        // Highlight problem corners from coaching data
        const bz = DATA.braking_zones || [];
        const focusPcts = coachingData.map(c => c.pct);

        // Draw all braking zones as small dots
        for (const zone of bz) {
            const pct = zone.pct;
            const idx = Math.round((pct / 100) * (points.length - 1));
            if (idx < 0 || idx >= points.length) continue;
            const pt = points[idx];
            const isFocus = focusPcts.some(fp => Math.abs(fp - pct) < 3);

            ctx.beginPath();
            ctx.arc(toX(pt.lon), toY(pt.lat), isFocus ? 8 : 4, 0, Math.PI * 2);
            ctx.fillStyle = isFocus ? '#ff1744' : '#448aff40';
            ctx.fill();

            // Label focus corners
            if (isFocus) {
                const label = zone.turn_name || 'T?';
                ctx.font = '11px Inter, system-ui, sans-serif';
                ctx.fillStyle = '#e8eaf0';
                ctx.textAlign = 'center';
                ctx.fillText(label, toX(pt.lon), toY(pt.lat) - 12);
            }
        }

        // Draw S/F line indicator
        if (points.length > 0) {
            const sf = points[0];
            ctx.beginPath();
            ctx.arc(toX(sf.lon), toY(sf.lat), 4, 0, Math.PI * 2);
            ctx.fillStyle = '#00e676';
            ctx.fill();
        }
    }

// ─── Initialize Summary View ─────────────────────────────────────────────────
    const coachingData = buildCoachingData();
    renderHeroes();
    renderNextFocus(coachingData);
    renderFocusCards(coachingData);
    renderMiniMap(coachingData);
})();
'''


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

def generate_report_cli():
    """CLI entry point: tenths report <file.ibt>"""
    import sys
    import os

    if len(sys.argv) < 2:
        print("Usage: tenths report <file.ibt>")
        print("  Generates session_report.html in the session output directory.")
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
        # Fallback: minimal file_info
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

    # Generate report (with progression if available)
    session_dir = os.path.join(TELEMETRY_ROOT, file_info['car'], file_info['track'], file_info['date'])
    os.makedirs(session_dir, exist_ok=True)

    # Try to compute progression
    progression = None
    try:
        from tenths.summary import generate_session_summary, compute_progression
        summary = generate_session_summary(data, file_info, track_map, race_result)
        progression = compute_progression(summary, session_dir)
    except Exception:
        pass  # Non-critical — report works without progression

    html = generate_report(data, file_info, track_map, race_result, progression=progression)

    # Write to session directory
    report_path = os.path.join(session_dir, "session_report.html")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Report generated: {report_path}")
    print(f"  Track map points: {len(data.get('gps_trace', []))}")
    print(f"  Braking zones: {len(data.get('braking_zones', []))}")
    print(f"  Open in browser to view.")
