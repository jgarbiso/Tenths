"""
Generate Session Notes — Automated Telemetry Processing (Phase 1)
===================================================================
Finds unprocessed .ibt files, analyzes them, generates complete
session_notes.md with turn names, baselines, and coaching flags.

Usage:
    python tools/generate_session_notes.py                    # process all pending
    python tools/generate_session_notes.py --dry-run          # preview without writing
    python tools/generate_session_notes.py "path/to/file.ibt" # process specific file

Run from: c:\\Users\\justi\\Documents\\iRacing\\telemetry

Requirements:
    python -m pip install pyirsdk pandas
"""

import os
import sys
import re
import glob
import shutil

from tenths.analyzer import analyze, fmt_time, parse_ibt
from tenths.track_map import load_track_map, get_turn_name
from tenths.report import generate_report
from tenths.summary import generate_session_summary, write_session_summary
from tenths.track_map_generator import generate_skeleton_track_map, write_skeleton_track_map

# ── Config ────────────────────────────────────────────────────────────────────
from tenths.config import (
    TELEMETRY_ROOT, ARCHIVE_DIR, MIN_SESSION_SIZE, DOWNLOADS_DIR,
    REQUIRED_ARTIFACTS, session_output_dir, is_metric,
)
from tenths.units import (
    distance_display, speed_display, temp_display, to_display_units,
)

FILENAME_PATTERN = re.compile(
    r'^(.+?)_(.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}-\d{2}-\d{2})(.*?)(\.\w+)$'
)


# ── File Discovery ────────────────────────────────────────────────────────────
def find_ibt_files(specific_path=None):
    """Find .ibt files to process."""
    if specific_path:
        if os.path.exists(specific_path):
            return [specific_path]
        return []

    # Find all .ibt in telemetry root
    files = []
    for f in os.listdir(TELEMETRY_ROOT):
        if f.endswith('.ibt') and os.path.isfile(os.path.join(TELEMETRY_ROOT, f)):
            filepath = os.path.join(TELEMETRY_ROOT, f)
            if os.path.getsize(filepath) >= MIN_SESSION_SIZE:
                files.append(filepath)
    return sorted(files, key=os.path.getmtime)


def parse_filename(filepath):
    """Parse iRacing filename into components."""
    filename = os.path.basename(filepath)
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None
    car, track, date_str, time_str, suffix, ext = match.groups()
    return {
        'car': car.strip().replace(' ', '_'),
        'track': track.strip().replace(' ', '_'),
        'date': date_str,
        'time': time_str,
        'filename': filename,
    }


# ── Baseline Loader ──────────────────────────────────────────────────────────
def load_baseline(car, track):
    """Load previous session baseline for comparison."""
    track_dir = os.path.join(TELEMETRY_ROOT, car, track)
    if not os.path.isdir(track_dir):
        return None

    # Find all session_notes.md files, sorted by date (most recent first)
    notes_files = []
    for date_dir in sorted(os.listdir(track_dir), reverse=True):
        notes_path = os.path.join(track_dir, date_dir, "session_notes.md")
        if os.path.exists(notes_path):
            notes_files.append((date_dir, notes_path))

    if not notes_files:
        return None

    # Parse the most recent one for baseline data
    latest_date, latest_path = notes_files[0]
    with open(latest_path, 'r', encoding='utf-8') as f:
        content = f.read()

    baseline = {'date': latest_date, 'path': latest_path}

    # Extract PB time (look for "**Best:**" pattern)
    pb_match = re.search(r'\*\*Best:\*\*\s*(\d+:\d+\.\d+)', content)
    if pb_match:
        parts = pb_match.group(1).split(':')
        baseline['pb_time'] = float(parts[0]) * 60 + float(parts[1])

    # Extract cleanest ABS
    clean_match = re.search(r'\*\*Cleanest:\*\*\s*(\d+)\s*ABS', content)
    if clean_match:
        baseline['cleanest_abs'] = int(clean_match.group(1))

    # Extract T2Peak values from braking zone tables
    t2peak_pattern = re.compile(r'\|\s*([\d.]+)%.*?\|\s*([\d.]+)s\s*\|')
    baseline['t2peak'] = {}
    for m in t2peak_pattern.finditer(content):
        try:
            pct = float(m.group(1))
            t2p = float(m.group(2))
            if 0 < t2p < 10:  # sanity check
                baseline['t2peak'][pct] = t2p
        except ValueError:
            pass

    return baseline


# ── Lap Selection ─────────────────────────────────────────────────────────────
def select_display_laps(lap_results, best_lap, max_rows=12):
    """Select which laps to show in the summary table."""
    if not lap_results:
        return []

    valid = [r for r in lap_results if r['time'] > 0]
    if not valid:
        return []

    best_time = min(r['time'] for r in valid)
    cleanest = min(valid, key=lambda r: r['abs'] if r['time'] < best_time + 3 else 9999)

    selected_indices = set()

    # Always include: first valid, best, cleanest
    selected_indices.add(0)  # first valid
    for i, r in enumerate(valid):
        if r['lap'] == best_lap:
            selected_indices.add(i)
        if r == cleanest:
            selected_indices.add(i)

    # Include session-best milestones (laps that were fastest at the time)
    running_best = float('inf')
    for i, r in enumerate(valid):
        if r['time'] < running_best:
            running_best = r['time']
            selected_indices.add(i)

    # Include last 3 laps
    for i in range(max(0, len(valid) - 3), len(valid)):
        selected_indices.add(i)

    # Skip laps >10% slower than best
    selected_indices = {i for i in selected_indices if valid[i]['time'] < best_time * 1.10}

    # Cap at max_rows
    selected = sorted(selected_indices)
    if len(selected) > max_rows:
        # Keep first, best, cleanest, and last few
        keep = {0, selected[-1], selected[-2], selected[-3]}
        for i, r in enumerate(valid):
            if r['lap'] == best_lap:
                keep.add(i)
            if r == cleanest:
                keep.add(i)
        remaining = [i for i in selected if i not in keep]
        selected = sorted(keep | set(remaining[:max_rows - len(keep)]))

    return [valid[i] for i in sorted(selected)]


# ── Markdown Generator ────────────────────────────────────────────────────────
def generate_notes(data, file_info, track_map, baseline, dry_run=False):
    """Generate the complete session_notes.md content.

    UNITS: this is a display boundary. `data` must already have been through
    `to_display_units()` — the caller does that — so its `*_mph` values are in
    whichever unit `spd_unit` names. Never hardcode a unit label here. Full rules:
    the module docstring in `tenths/units.py`.
    """
    metric = is_metric()
    _, spd_unit = speed_display(0.0, metric=metric)
    _, temp_unit = temp_display(0.0, metric=metric)

    # Use session_info from .ibt header for proper display names
    si = data.get('session_info', {})
    car_display = si.get('car_screen_name') or file_info['car'].replace('_', ' ')
    track_display_name = si.get('track_display_name') or file_info['track'].replace('_', ' ').title()
    track_config = si.get('track_config_name', '')
    track_display = f"{track_display_name}, {track_config}" if track_config else track_display_name
    event_type = si.get('event_type', 'Practice')
    car_class = si.get('car_class_short') or data.get('car_class', '')
    # Don't show class if it's the same as the car name (single-make series)
    show_class = car_class and car_class.lower().replace(' ', '') != car_display.lower().replace(' ', '')

    date = file_info['date']
    time_str = file_info['time']
    filesize_mb = data.get('filesize_mb', 0)

    is_first_session = baseline is None
    valid_results = [r for r in data['lap_results'] if r['time'] > 0]
    best_result = min(valid_results, key=lambda x: x['time'])
    cleanest_result = min(valid_results, key=lambda x: x['abs'] if x['time'] < best_result['time'] + 3 else 9999)

    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(f"# {car_display} — {track_display} — {date}")
    lines.append("")
    lines.append("## Session Info")
    lines.append(f"- **Car:** {car_display}")
    lines.append(f"- **Track:** {track_display}")
    if show_class:
        lines.append(f"- **Class:** {car_class}")
    lines.append(f"- **Session Type:** {event_type}")
    if is_first_session:
        lines.append(f"- **First session at this track**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Lap Table ─────────────────────────────────────────────────────────────
    time_display = time_str.replace('-', ':')[:5]
    lines.append(f"## {event_type} ({time_display}) — {filesize_mb:.1f}MB, {len(data['valid_laps'])} valid laps")
    lines.append("")
    if is_first_session:
        lines.append("### Learning Curve")
        lines.append("")
    lines.append("| Lap | Time | ABS | Max Speed | Notes |")
    lines.append("|---|---|---|---|---|")

    display_laps = select_display_laps(data['lap_results'], data['best_lap'])
    for r in display_laps:
        time_str_fmt = f"{int(r['time']//60)}:{r['time']%60:04.1f}"
        notes = []
        if r['lap'] == best_result['lap']:
            notes.append("**Best lap**")
        if r == cleanest_result and r['lap'] != best_result['lap']:
            notes.append("**Cleanest**")
        if r == valid_results[0] and is_first_session:
            notes.append("First hot lap")

        time_cell = f"**{time_str_fmt}**" if r['lap'] == best_result['lap'] else time_str_fmt
        abs_cell = f"**{r['abs']}**" if r == cleanest_result else str(r['abs'])
        notes_str = ", ".join(notes) if notes else ""

        lines.append(f"| {r['lap']} | {time_cell} | {abs_cell} | {r['max_speed_mph']:.0f} {spd_unit} | {notes_str} |")

    lines.append("")
    lines.append(f"**Best:** {fmt_time(best_result['time'])} (Lap {best_result['lap']})")
    lines.append(f"**Cleanest:** {cleanest_result['abs']} ABS (Lap {cleanest_result['lap']})")
    lines.append(f"**ABS Trend:** {data['abs_trend']['early_avg']:.0f} avg first half → {data['abs_trend']['late_avg']:.0f} avg second half ({data['abs_trend']['delta']:+.0f})")

    if is_first_session and len(valid_results) > 3:
        first_time = valid_results[0]['time']
        improvement = first_time - best_result['time']
        lines.append(f"**Improvement:** {fmt_time(first_time)} → {fmt_time(best_result['time'])} = **{improvement:.1f} seconds gained**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Braking Zones ─────────────────────────────────────────────────────────
    lines.append(f"## Braking Zones (Best Lap {data['best_lap']}) "
                 f"[{data.get('physics_profile') or data['car_class']} Physics]")
    lines.append("")

    if data['car_class'] == "GT4":
        lines.append("| Zone | Turn | Entry | Min | ABS | T2Peak | Coast | TIn Brk | ApxBrk | Notes |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for z in data['braking_zones']:
            turn = get_turn_name(track_map, z['pct'])
            t2p = f"{z['t2peak']:.2f}s" if z['t2peak'] is not None else "N/A"
            coast = f"{z['coast_time']:.2f}s" if z.get('coast_time') is not None else "N/A"
            turnin = f"{z['turnin_brake']:.0f}%" if z.get('turnin_brake') is not None else "N/A"
            notes = ", ".join(z['notes']) if z['notes'] else ""
            lines.append(f"| {z['pct']:.1f}% | **{turn}** | {z['entry_mph']:.0f} {spd_unit} | {z['min_mph']:.0f} {spd_unit} | {z['abs']} | {t2p} | {coast} | {turnin} | {z['apex_brake']:.0f}% | {notes} |")
    else:
        lines.append("| Zone | Turn | Entry | Min | ABS | Brk2Shft | MaxDS RPM | Apex RPM | Notes |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for z in data['braking_zones']:
            turn = get_turn_name(track_map, z['pct'])
            b2s = f"{z['brake_to_shift']:.2f}s" if z['brake_to_shift'] is not None and z['brake_to_shift'] >= 0 else "—"
            ds_rpm = f"{z['max_ds_rpm']:.0f}" if z['max_ds_rpm'] > 0 else "N/A"
            notes = ", ".join(z['notes']) if z['notes'] else ""
            lines.append(f"| {z['pct']:.1f}% | **{turn}** | {z['entry_mph']:.0f} {spd_unit} | {z['min_mph']:.0f} {spd_unit} | {z['abs']} | {b2s} | {ds_rpm} | {z['apex_rpm']:.0f} | {notes} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Trail Braking ─────────────────────────────────────────────────────────
    lines.append(f"## Trail Braking (Best Lap {data['best_lap']})")
    lines.append("")
    lines.append("| Zone | Turn | Brake | Lateral G | Diagnosis |")
    lines.append("|---|---|---|---|---|")
    for t in data['trail_braking']:
        turn = get_turn_name(track_map, t['pct'])
        lines.append(f"| {t['pct']:.1f}% | **{turn}** | {t['brake']:.0f}% | {t['lat_g']:.2f}G | {t['diagnosis']} |")
    good_count = sum(1 for t in data['trail_braking'] if t['diagnosis'] == 'Good')
    lines.append(f"\n{good_count} \"Good\" zones on best lap.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Corner Variance ───────────────────────────────────────────────────────
    lines.append(f"## Corner Variance ({len(data['valid_laps'])} laps)")
    lines.append("")
    lines.append("| Zone | Turn | Avg | Best | Loss | StdDev | Priority |")
    lines.append("|---|---|---|---|---|---|---|")
    for cv in data['corner_variance']:
        turn = get_turn_name(track_map, cv['pct'])
        priority = "**HIGH**" if cv['loss'] > 0.5 else ("Medium" if cv['loss'] > 0.3 else "")
        lines.append(f"| {cv['pct']:.1f}% | **{turn}** | {cv['avg']:.2f}s | {cv['best']:.2f}s | {cv['loss']:.2f}s | {cv['std']:.2f}s | {priority} |")
    total_loss = sum(cv['loss'] for cv in data['corner_variance'])
    lines.append(f"\n**Total recoverable: {total_loss:.2f}s**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── GPS Track Position Map ────────────────────────────────────────────────
    if data['gps_trace']:
        lines.append(f"## Track Position Map (GPS — Best Lap {data['best_lap']})")
        lines.append("")
        if data['track_length_m'] > 0:
            dist_val, dist_unit = distance_display(data['track_length_m'], metric=metric)
            lines.append(f"Track length: {data['track_length_m']:.0f}m ({dist_val:.2f}{dist_unit})")
            lines.append("")
        lines.append("### Braking Zone GPS Coordinates")
        lines.append("")
        lines.append("| Zone | Turn | Dist | Lat | Lon | Entry | Min |")
        lines.append("|---|---|---|---|---|---|---|")
        for z in data['braking_zones']:
            if z['lat'] != 0:
                turn = get_turn_name(track_map, z['pct'])
                lines.append(f"| {z['entry_pct']:.1f}% | **{turn}** | {z['dist_m']:.0f}m | {z['lat']:.6f} | {z['lon']:.6f} | {z['entry_mph']:.0f} {spd_unit} | {z['min_mph']:.0f} {spd_unit} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Tire Temps ────────────────────────────────────────────────────────────
    if data['tire_temps']:
        lines.append(f"## Tire Temps (Best Lap, under-load, {temp_unit})")
        lines.append("")
        lines.append("| Corner | Inner | Mid | Outer | Avg |")
        lines.append("|---|---|---|---|---|")
        for corner in ['LF', 'RF', 'LR', 'RR']:
            if corner in data['tire_temps']:
                t = data['tire_temps'][corner]
                lines.append(f"| {corner} | {t['inner']:.1f} | {t['mid']:.1f} | {t['outer']:.1f} | {t['avg']:.1f} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── GT4 Brake Shape ───────────────────────────────────────────────────────
    if data['car_class'] == "GT4" and data['braking_zones']:
        lines.append("## GT4 Brake Shape")
        lines.append("")
        lines.append("| Zone | Turn | T2Peak | Target | Status |")
        lines.append("|---|---|---|---|---|")
        for z in data['braking_zones']:
            if z['t2peak'] is not None:
                turn = get_turn_name(track_map, z['pct'])
                status = "✅ AT TARGET" if z['t2peak'] <= 0.4 else ("Close" if z['t2peak'] <= 0.55 else "Needs work")
                lines.append(f"| {z['pct']:.0f}% | **{turn}** | {z['t2peak']:.2f}s | <0.4s | {status} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Key Findings ──────────────────────────────────────────────────────────
    lines.append("## Key Findings")
    lines.append("")
    findings = generate_findings(data, baseline, is_first_session, valid_results, best_result, cleanest_result)
    for i, finding in enumerate(findings, 1):
        lines.append(f"{i}. {finding}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Targets ───────────────────────────────────────────────────────────────
    lines.append("## Targets for Next Session")
    lines.append("")
    targets = generate_targets(data, best_result, track_map)
    for target in targets:
        lines.append(f"- [ ] {target}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Files ─────────────────────────────────────────────────────────────────
    lines.append("## Files")
    lines.append("")
    lines.append("| File | Description |")
    lines.append("|---|---|")
    lines.append(f"| `_archive/{file_info['filename']}` | Practice ({filesize_mb:.1f}MB) |")
    lines.append(f"| `session_notes.md` | This file |")
    lines.append("")

    return "\n".join(lines)


# ── Rule-Based Findings ───────────────────────────────────────────────────────
def generate_findings(data, baseline, is_first, valid_results, best_result, cleanest_result):
    """Generate key findings from data using rules."""
    findings = []

    # First session improvement
    if is_first and len(valid_results) > 3:
        first_time = valid_results[0]['time']
        improvement = first_time - best_result['time']
        findings.append(f"**First session** — {improvement:.1f}s gained over {len(data['valid_laps'])} laps")

    # PB detection
    if baseline and 'pb_time' in baseline:
        if best_result['time'] < baseline['pb_time']:
            findings.append(f"**NEW PB:** {fmt_time(best_result['time'])} (prev: {fmt_time(baseline['pb_time'])})")
        else:
            delta = best_result['time'] - baseline['pb_time']
            findings.append(f"Best lap {fmt_time(best_result['time'])} — {delta:.1f}s off PB ({fmt_time(baseline['pb_time'])})")

    # Cleanest ABS
    if baseline and 'cleanest_abs' in baseline:
        if cleanest_result['abs'] < baseline['cleanest_abs']:
            findings.append(f"**NEW CLEANEST:** {cleanest_result['abs']} ABS (prev: {baseline['cleanest_abs']})")

    # High priority corners
    high_corners = [cv for cv in data['corner_variance'] if cv['loss'] > 0.5]
    if high_corners:
        names = ", ".join(f"{cv['pct']:.0f}%" for cv in high_corners[:2])
        findings.append(f"HIGH PRIORITY corners: {names} — >{high_corners[0]['loss']:.2f}s time loss")

    # Brake shape at target
    at_target = [z for z in data['braking_zones'] if z['t2peak'] is not None and z['t2peak'] <= 0.4]
    if at_target and data['car_class'] == "GT4":
        findings.append(f"Brake shape AT TARGET on {len(at_target)} zone(s)")
    elif data['car_class'] == "GT4":
        close = [z for z in data['braking_zones'] if z['t2peak'] is not None and z['t2peak'] <= 0.55]
        if close:
            findings.append(f"Brake shape close to target on {len(close)} zone(s) (best: {min(z['t2peak'] for z in close):.2f}s)")

    # ABS trend
    if data['abs_trend']['delta'] < -50:
        findings.append(f"Strong ABS improvement through session ({data['abs_trend']['delta']:+.0f})")
    elif data['abs_trend']['delta'] > 50:
        findings.append(f"ABS worsening through session ({data['abs_trend']['delta']:+.0f}) — fatigue?")

    # Oversteer flags
    oversteer = [t for t in data['trail_braking'] if 'oversteer' in t['diagnosis'].lower()]
    if oversteer:
        findings.append(f"Oversteer risk at {len(oversteer)} zone(s) — release brake before rotation")

    # Best laps at end
    if valid_results and best_result == valid_results[-1] or (len(valid_results) > 3 and best_result in valid_results[-3:]):
        findings.append("Best laps came late — still finding time at end of session")

    return findings if findings else ["Session completed — no notable flags"]


def generate_targets(data, best_result, track_map=None):
    """Generate targets for next session."""
    targets = []

    # Lap time target
    target_time = best_result['time'] - 0.5
    mins = int(target_time // 60)
    secs = target_time % 60
    targets.append(f"Best lap under {mins}:{secs:04.1f}")

    # Highest ABS zone
    if data['braking_zones']:
        worst_abs_zone = max(data['braking_zones'], key=lambda z: z['abs'])
        if worst_abs_zone['abs'] > 30:
            turn = get_turn_name(track_map, worst_abs_zone['pct'])
            targets.append(f"Reduce ABS at {turn} to under {max(30, worst_abs_zone['abs']//2)}")

    # Corner variance
    high_var = [cv for cv in data['corner_variance'] if cv['loss'] > 0.5]
    for cv in high_var[:2]:
        turn = get_turn_name(track_map, cv['pct'])
        targets.append(f"{turn} time loss under 0.3s (currently {cv['loss']:.2f}s)")

    # T2Peak
    if data['car_class'] == "GT4":
        slow_brake = [z for z in data['braking_zones'] if z['t2peak'] is not None and z['t2peak'] > 0.6]
        if slow_brake:
            worst = max(slow_brake, key=lambda z: z['t2peak'])
            turn = get_turn_name(track_map, worst['pct'])
            targets.append(f"T2Peak under {max(0.4, worst['t2peak']-0.2):.1f}s at {turn}")

    return targets


# Removed 2026-08-01: update_track_file() appended a row to each track's .md
# "Performance History" table after every day group. The RR-006 per-session
# rewrite dropped its only caller, leaving it dead.
#
# It is not being restored, for two reasons:
#   1. It wrote into the bundled `tracks` directory, which in a frozen build is
#      inside the install folder — overwritten on upgrade, removed on uninstall.
#      See config.USER_TRACKS_DIR for why that path is no longer written to.
#   2. It was already broken on Windows: it called strftime('%b %-d'), and the
#      %-d directive raises ValueError on Windows. The line below it was a
#      workaround that could never execute.
#
# If per-track history tables are wanted again, they need a user-writable
# destination and a portable date format.


# ── Race Result Auto-Matching ─────────────────────────────────────────────────


def find_race_result(session_info):
    """
    Auto-find a race result file matching this session's subsession_id.
    Searches Downloads folder for eventresult_<subsession_id>*.csv or .json.
    """
    subsession_id = session_info.get('subsession_id', 0)
    if not isinstance(subsession_id, int) or subsession_id <= 0:
        return None

    if not os.path.isdir(DOWNLOADS_DIR):
        return None

    # Look for CSV first (simpler to parse), then JSON
    for pattern in [f"eventresult_{subsession_id}*.csv", f"eventresult-{subsession_id}.json"]:
        matches = glob.glob(os.path.join(DOWNLOADS_DIR, pattern))
        if matches:
            return matches[0]

    return None


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    from tenths.config import configure_console
    configure_console()

    dry_run = '--dry-run' in sys.argv
    specific = None

    # Collect non-flag arguments — these form the file path
    # Handles paths with spaces whether quoted correctly or split by shell
    path_parts = []
    for arg in sys.argv[1:]:
        if arg.startswith('--'):
            continue
        path_parts.append(arg)

    if path_parts:
        # Try the parts as a single joined path first (handles shell-split spaces)
        joined = ' '.join(path_parts)
        if os.path.exists(joined):
            specific = joined
        # Then try each part individually (handles multiple separate files — pick first valid)
        elif len(path_parts) == 1 and os.path.exists(path_parts[0]):
            specific = path_parts[0]
        else:
            # Last resort: maybe the path is correct but doesn't exist
            # Give the user a useful error
            print(f"File not found: {joined}")
            return

    if dry_run:
        print("=== DRY RUN MODE ===\n")

    # Find files
    ibt_files = find_ibt_files(specific)
    if not ibt_files:
        print("No .ibt files to process.")
        return

    print(f"Found {len(ibt_files)} file(s) to process.\n")

    # Process each file individually — every session gets its own output folder
    succeeded = 0
    skipped = 0
    failed = 0

    for filepath in ibt_files:
        file_info = parse_filename(filepath)
        if not file_info:
            print(f"  SKIP: Could not parse filename: {os.path.basename(filepath)}")
            skipped += 1
            continue

        car = file_info['car']
        track = file_info['track']
        date = file_info['date']
        time_str = file_info['time']
        filesize_mb = os.path.getsize(filepath) / 1024 / 1024

        print(f"\n{'='*60}")
        print(f"SESSION: {car} / {track} / {date} {time_str} ({filesize_mb:.1f}MB)")
        print(f"{'='*60}")

        try:
            data = analyze(filepath)
            if not data:
                print(f"  No valid laps — skipping")
                if not dry_run:
                    os.makedirs(ARCHIVE_DIR, exist_ok=True)
                    shutil.move(filepath, os.path.join(ARCHIVE_DIR, os.path.basename(filepath)))
                skipped += 1
                continue

            # Store filesize for notes
            data['filesize_mb'] = filesize_mb

            print(f"  Valid laps: {len(data['valid_laps'])}, Best: Lap {data['best_lap']}, "
                  f"Type: {data.get('session_info', {}).get('event_type', '?')}")

            # Auto-find race result
            race_result = None
            si = data.get('session_info', {})
            result_file = find_race_result(si)
            if result_file:
                from tenths.results import parse_result
                race_result = parse_result(result_file, my_cust_id=si.get('driver_id'))
                if race_result and race_result.get('my_result'):
                    me = race_result['my_result']
                    print(f"  Race result: P{me['finish_pos']}/{race_result['entries']}, "
                          f"iR {me.get('old_irating',0)}->{me.get('new_irating',0)}")

            # Determine output directory (per-session, with collision handling)
            session_dir = session_output_dir(TELEMETRY_ROOT, car, track, date, time_str)

            if dry_run:
                print(f"\n  Would write to: {session_dir}")
                print(f"  Artifacts: {', '.join(REQUIRED_ARTIFACTS)}")
                succeeded += 1
                continue

            os.makedirs(session_dir, exist_ok=True)

            # Load track map
            track_map = load_track_map(track)
            if not track_map and data.get('braking_zones'):
                si = data.get('session_info', {})
                try:
                    skeleton = generate_skeleton_track_map(data, si)
                    track_slug = track.lower().replace(' ', '_')
                    written = write_skeleton_track_map(skeleton, track_slug)
                    if written:
                        print(f"  Auto-generated track map: {os.path.basename(written)}")
                        track_map = load_track_map(track)
                except Exception as e:
                    print(f"  Warning: track map generation failed: {e}")

            baseline = load_baseline(car, track)

            # 1. Session notes (per-session, not day-level)
            notes_content = generate_day_notes(
                [(file_info, data, race_result)], car, track, date, track_map, baseline)
            notes_path = os.path.join(session_dir, "session_notes.md")
            with open(notes_path, 'w', encoding='utf-8') as f:
                f.write(notes_content)
            print(f"  Created: session_notes.md")

            # 2. HTML report
            progression = None
            try:
                summary_for_prog = generate_session_summary(data, file_info, track_map, race_result)
                from tenths.summary import compute_progression
                progression = compute_progression(summary_for_prog, session_dir)
            except Exception:
                pass

            report_html = generate_report(data, file_info, track_map, race_result, progression=progression)
            report_path = os.path.join(session_dir, "session_report.html")
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_html)
            print(f"  Created: session_report.html")

            # 3. JSON summary
            summary = generate_session_summary(data, file_info, track_map, race_result)
            write_session_summary(summary, session_dir)
            print(f"  Created: session_summary.json")

            # Copy race result file to session dir if found
            if race_result and race_result.get('filepath'):
                src = race_result['filepath']
                dst = os.path.join(session_dir, os.path.basename(src))
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    print(f"  Copied race result: {os.path.basename(src)}")

            # Verify all required artifacts before archiving (RR-007)
            missing = [name for name in REQUIRED_ARTIFACTS
                       if not os.path.exists(os.path.join(session_dir, name))]
            if missing:
                print(f"  ERROR: Missing artifacts {missing} — source NOT archived")
                failed += 1
                continue

            # Archive the .ibt only after all artifacts are confirmed
            os.makedirs(ARCHIVE_DIR, exist_ok=True)
            shutil.move(filepath, os.path.join(ARCHIVE_DIR, os.path.basename(filepath)))
            print(f"  Archived: _archive/{os.path.basename(filepath)}")
            succeeded += 1

        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
            continue

    # Batch summary
    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE: {succeeded} succeeded, {skipped} skipped, {failed} failed")
    print(f"{'='*60}")

    # Regenerate master index so new sessions appear
    if not dry_run and succeeded > 0:
        try:
            from tenths.index_generator import generate_master_index
            generate_master_index()
        except Exception:
            pass  # Non-critical


def generate_day_notes(sessions, car, track, date, track_map, baseline):
    """
    Generate a single session_notes.md for all sessions on this day.
    Each session gets its own section (Practice, Qualifying, Race).
    """
    # The analyzer works in SI; the notes render display units. Convert once up
    # front so every table below formats display values.
    sessions = [
        (fi, to_display_units(data, metric=is_metric()), rr)
        for fi, data, rr in sessions
    ]

    # Use the first session's data for the header metadata
    first_fi, first_data, _ = sessions[0]
    si = first_data.get('session_info', {})

    car_display = si.get('car_screen_name') or car.replace('_', ' ')
    track_display_name = si.get('track_display_name') or track.replace('_', ' ').title()
    track_config = si.get('track_config_name', '')
    track_display = f"{track_display_name}, {track_config}" if track_config else track_display_name
    car_class = si.get('car_class_short') or first_data.get('car_class', '')
    show_class = car_class and car_class.lower().replace(' ', '') != car_display.lower().replace(' ', '')

    is_first_session = baseline is None

    all_parts = []

    # Header (one per file)
    header_lines = []
    header_lines.append(f"# {car_display} — {track_display} — {date}")
    header_lines.append("")
    header_lines.append("## Session Info")
    header_lines.append(f"- **Car:** {car_display}")
    header_lines.append(f"- **Track:** {track_display}")
    if show_class:
        header_lines.append(f"- **Class:** {car_class}")

    # Check if any session has race results
    race_result_data = None
    for fi, d, rr in sessions:
        if rr and rr.get('my_result'):
            race_result_data = rr
            break

    if race_result_data:
        me = race_result_data['my_result']
        header_lines.append(f"- **Series:** {race_result_data.get('series', '')}")
        header_lines.append(f"- **SOF:** {race_result_data.get('sof', 0)}")
        header_lines.append(f"- **Started:** P{me['start_pos']} / {race_result_data['entries']} cars")
        header_lines.append(f"- **Finished:** P{me['finish_pos']} / {race_result_data['entries']} ({me['laps_completed']} laps, {me['incidents']} incidents)")
        if me.get('old_irating') and me.get('new_irating'):
            delta = me['new_irating'] - me['old_irating']
            header_lines.append(f"- **iRating:** {me['old_irating']} -> {me['new_irating']} ({delta:+d})")

    if is_first_session:
        header_lines.append(f"- **First session at this track**")
    header_lines.append("")
    header_lines.append("---")
    header_lines.append("")

    all_parts.append("\n".join(header_lines))

    # Race result context table (if available)
    if race_result_data:
        from tenths.results import generate_race_context_markdown
        race_md = generate_race_context_markdown(race_result_data)
        if race_md:
            all_parts.append(race_md)
            all_parts.append("\n---\n\n")

    # Each session gets its own analysis section
    for fi, data, rr in sessions:
        session_notes = generate_notes(data, fi, track_map, baseline, dry_run=False)
        # Strip the header from generate_notes (we already have one)
        # Find the first "---" separator and take everything after the Session Info block
        lines = session_notes.split('\n')
        # Find the lap table section (starts with "## Practice" or "## Race" etc.)
        start_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('## ') and any(t in line for t in ('Practice', 'Race', 'Qualify', 'Test', 'Lone Qualify', 'Warmup')):
                start_idx = i
                break
        session_section = '\n'.join(lines[start_idx:])
        all_parts.append(session_section)

    return '\n'.join(all_parts)


if __name__ == "__main__":
    main()
