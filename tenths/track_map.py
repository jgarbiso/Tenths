"""
Track Map Parser — Maps telemetry percentages to turn names.
==============================================================
Primary source: bundled trackLandmarksData.json (457 iRacing tracks with
corner positions in meters, from CrewChief community data).

Fallback: hand-tuned tracks/*.md files (legacy, used when landmark data
doesn't cover a track).

Usage:
    from track_map import load_track_map, get_turn_name
    track = load_track_map('roadatlanta_full')
    name = get_turn_name(track, 83.0)  # → 'T10'
"""

import os
import re
import sys
import json


def _resource_base():
    """Return the base directory for bundled resources.

    Handles both running from source and from a PyInstaller frozen exe.
    In a frozen app, PyInstaller extracts bundled data to sys._MEIPASS.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    # From source: this file lives at <root>/tenths/track_map.py
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Where track map files live
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_RESOURCE_BASE = _resource_base()

# Track map .md files — check both frozen (bundled at root/tracks) and source layouts
# An override must take precedence, so it comes first. Previously it was last
# and the loader stopped at the first directory that merely existed, so a
# bundled `tracks` folder shadowed it entirely.
TRACK_MAPS_DIRS = [
    os.environ.get('TENTHS_TRACKS_DIR', ''),        # user override wins
    os.path.join(_RESOURCE_BASE, "tracks"),         # frozen: <MEIPASS>/tracks
    os.path.join(os.path.dirname(_SCRIPT_DIR), "tracks"),  # source: <root>/tracks
]

# Bundled landmark data — check frozen (bundled) and source layouts
_LANDMARKS_CANDIDATES = [
    os.path.join(_RESOURCE_BASE, "data", "trackLandmarksData.json"),  # frozen: <MEIPASS>/data
    os.path.join(_SCRIPT_DIR, "data", "trackLandmarksData.json"),     # source: tenths/data
]
_LANDMARKS_PATH = next((p for p in _LANDMARKS_CANDIDATES if os.path.exists(p)), _LANDMARKS_CANDIDATES[-1])
_landmarks_cache = None  # Loaded once on first use


def _load_landmarks():
    """Load the bundled trackLandmarksData.json (cached after first call)."""
    global _landmarks_cache
    if _landmarks_cache is not None:
        return _landmarks_cache

    if not os.path.exists(_LANDMARKS_PATH):
        _landmarks_cache = {}
        return _landmarks_cache

    with open(_LANDMARKS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Build a lookup dict: irTrackName → entry
    _landmarks_cache = {}
    for entry in data.get('trackLandmarksData', []):
        ir_name = entry.get('irTrackName')
        if ir_name:
            _landmarks_cache[ir_name] = entry

    return _landmarks_cache


def _format_landmark_name(raw_names):
    """Convert landmark names like 'turn5', 'the_esses', 'canada_corner' to display names.

    Args:
        raw_names: list of landmark name strings from the JSON

    Returns:
        Tuple of (turn_label, display_name, full_name)
        e.g., ('T5', '', 'T5'), ('T10', 'Canada Corner', 'T10 Canada Corner'),
        or ('T5', 'Esses', 'T5 Esses') when a corner has both a number and a name.
    """
    if not raw_names:
        return ('?', '', '?')

    # Scan ALL names for a turn number (may be in any position, e.g. ['the_esses', 'turn5'])
    turn_label = ''
    for name in raw_names:
        turn_match = re.match(r'^turn(\d+[a-z]?)$', name.strip().lower())
        if turn_match:
            turn_label = f"T{turn_match.group(1).upper()}"
            break

    # Scan ALL names for a friendly (non-generic) name
    friendly = ''
    for name in raw_names:
        if re.match(r'^turn\d', name.strip().lower()):
            continue  # Skip generic 'turnX' — look for a real name
        # Convert 'canada_corner' → 'Canada Corner', 'the_esses' → 'The Esses'
        candidate = name.replace('_', ' ').strip().title()
        # Strip a leading "The " prefix only (word-boundary, not substring)
        if candidate.startswith('The '):
            candidate = candidate[4:]
        if candidate:
            friendly = candidate
            break

    # Combine turn number and name
    if turn_label and friendly:
        full = f"{turn_label} {friendly}"
    elif turn_label:
        full = turn_label
    elif friendly:
        full = friendly
    else:
        full = raw_names[0].replace('_', ' ').title()

    return (turn_label or full, friendly, full)


def _load_from_landmarks(venue_slug):
    """Load track zones from bundled landmark data.

    Args:
        venue_slug: iRacing track slug from .ibt filename (e.g., 'roadatlanta_full')

    Returns:
        List of zone dicts (same format as load_track_map), or empty list if not found.
    """
    landmarks = _load_landmarks()
    if not landmarks:
        return []

    # Convert slug: underscores → spaces to match CrewChief format
    lookup_key = venue_slug.replace('_', ' ').lower().strip()

    entry = landmarks.get(lookup_key)
    if not entry:
        return []

    track_length = entry.get('approximateTrackLength', 0)
    if track_length <= 0:
        return []

    zones = []
    for landmark in entry.get('trackLandmarks', []):
        dist_start = landmark.get('distanceRoundLapStart', 0)
        dist_end = landmark.get('distanceRoundLapEnd', 0)
        names = landmark.get('landmarkNames', [])

        # Convert distance to percentage
        pct_start = (dist_start / track_length) * 100
        pct_end = (dist_end / track_length) * 100
        pct_center = (pct_start + pct_end) / 2

        turn_label, friendly_name, full_name = _format_landmark_name(names)

        zones.append({
            'pct_center': pct_center,
            'pct_range': (pct_start, pct_end),
            'dist_range': (dist_start, dist_end),
            'turn': turn_label,
            'name': friendly_name,
            'full': full_name,
        })

    return zones


def load_track_map(venue_name):
    """
    Load a track map for the given venue.

    Lookup order:
    1. Bundled trackLandmarksData.json (457 tracks, exact slug match)
    2. Hand-tuned tracks/*.md files (legacy fallback)

    Returns a list of turn zones, or empty list if not found.
    Each zone: {
        'pct_center': float,          # midpoint of the zone as track %
        'pct_range': (start, end),    # zone span as track %
        'dist_range': (start, end) | None,  # zone span in meters (landmarks only)
        'turn': str,                  # short label, e.g. 'T5'
        'name': str,                  # friendly name, e.g. 'Canada Corner' (may be '')
        'full': str,                  # combined, e.g. 'T5 Canada Corner'
    }
    """
    # 1. Try bundled landmark data first (primary source)
    zones = _load_from_landmarks(venue_name)
    if zones:
        return zones

    # 2. Fall back to hand-tuned .md files
    return _load_from_md_file(venue_name)


def _md_candidates_in(tracks_dir, venue_name):
    """Candidate .md paths for a venue within one directory, best match first."""
    candidates = [
        os.path.join(tracks_dir, f"{venue_name}.md"),
        os.path.join(tracks_dir, f"{venue_name.replace(' ', '_')}.md"),
    ]
    needle = venue_name.lower().replace(' ', '')
    try:
        for name in sorted(os.listdir(tracks_dir)):
            if needle in name.lower().replace('_', '').replace(' ', ''):
                candidates.append(os.path.join(tracks_dir, name))
    except OSError:
        pass
    return candidates


def _load_from_md_file(venue_name):
    """Load track map from a tracks/*.md file (legacy fallback).

    Every configured directory is searched in order. Stopping at the first
    directory that merely existed meant a bundled `tracks` folder shadowed an
    override even when it did not contain the requested map.
    """
    filepath = None
    for tracks_dir in TRACK_MAPS_DIRS:
        if not tracks_dir or not os.path.isdir(tracks_dir):
            continue
        for candidate in _md_candidates_in(tracks_dir, venue_name):
            if os.path.exists(candidate):
                filepath = candidate
                break
        if filepath:
            break

    if not filepath:
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse the Turn Map table — look for the section header first
    zones = []

    # Find the Turn Map section
    turn_map_start = content.find("## Turn Map")
    if turn_map_start == -1:
        return []

    # Find the next section header (## ...) after Turn Map
    next_section = content.find("\n## ", turn_map_start + 10)
    if next_section == -1:
        turn_map_content = content[turn_map_start:]
    else:
        turn_map_content = content[turn_map_start:next_section]

    # Pattern matches rows like: | ~14-15% | **T1-T2** | TGR Corner | Right | ... |
    # or: | ~5% | **T1** | — | Right | ... |
    table_pattern = re.compile(
        r'\|\s*~?(\d+)(?:-(\d+))?%?\s*\|\s*\*?\*?([^|*]+?)\*?\*?\s*\|\s*([^|]*?)\s*\|'
    )

    for match in table_pattern.finditer(turn_map_content):
        pct_min = int(match.group(1))
        pct_max = int(match.group(2)) if match.group(2) else pct_min
        turn = match.group(3).strip()
        name = match.group(4).strip()

        # Skip header rows and separators
        if turn.lower() in ('turn', '---', '') or name.lower() in ('name', '---'):
            continue
        # Skip if pct_min is unreasonable (>100 means it's parsing wrong data)
        if pct_min > 100:
            continue

        pct_center = (pct_min + pct_max) / 2.0
        full_name = f"{turn} {name}".strip() if name and name != '—' else turn

        zones.append({
            'pct_center': pct_center,
            'pct_range': (pct_min, pct_max),
            'dist_range': None,  # .md files don't carry distance data (landmarks do)
            'turn': turn,
            'name': name if name != '—' else '',
            'full': full_name,
        })

    return zones


def get_turn_name(track_map, pct, tolerance=5.0):
    """
    Given a track percentage, return the closest turn name.
    Returns the full turn name (e.g., 'T1-T2 TGR Corner') or a fallback with percentage.

    Matching strategy:
    1. If pct falls within any zone's defined range → use that zone (exact match)
    2. Otherwise, find the closest zone center within tolerance (fuzzy fallback)

    Args:
        track_map: list from load_track_map()
        pct: track position percentage (0-100)
        tolerance: max distance in % to consider a match (default 5%)
    """
    if not track_map:
        return f"({pct:.1f}%)"

    # Phase 1: exact range match — pct falls within a zone's defined range
    for zone in track_map:
        low = zone['pct_range'][0]
        high = zone['pct_range'][1]
        if low <= pct <= high:
            return zone['full']

    # Phase 2: closest center within tolerance (fallback for gaps between zones)
    # Braking typically happens 1-3% before a corner, so we need some tolerance
    best_match = None
    best_dist = tolerance + 1

    for zone in track_map:
        dist = abs(pct - zone['pct_center'])
        if dist < best_dist:
            best_dist = dist
            best_match = zone

    if best_match and best_dist <= tolerance:
        return best_match['full']

    return f"({pct:.1f}%)"


def get_turn_short(track_map, pct, tolerance=5.0):
    """Like get_turn_name but returns just the turn number (e.g., 'T1-T2')."""
    if not track_map:
        return f"{pct:.1f}%"

    # Phase 1: exact range match
    for zone in track_map:
        if zone['pct_range'][0] <= pct <= zone['pct_range'][1]:
            return zone['turn']

    # Phase 2: closest center within tolerance
    best_match = None
    best_dist = tolerance + 1

    for zone in track_map:
        dist = abs(pct - zone['pct_center'])
        if dist < best_dist:
            best_dist = dist
            best_match = zone

    if best_match and best_dist <= tolerance:
        return best_match['turn']
    return f"{pct:.1f}%"


if __name__ == "__main__":
    # Test / debug helper: python -m tenths.track_map <track_slug>
    import sys
    track_name = sys.argv[1] if len(sys.argv) > 1 else "roadatlanta_full"
    zones = load_track_map(track_name)
    if not zones:
        print(f"No track map found for '{track_name}'")
        print(f"Searched landmarks: {_LANDMARKS_PATH}")
        print(f"Searched dirs: {TRACK_MAPS_DIRS}")
    else:
        print(f"Track map: {track_name} ({len(zones)} zones)")
        for z in zones:
            lo, hi = z['pct_range']
            print(f"  {lo:5.1f}-{hi:5.1f}%  {z['full']}")
        # Test lookups
        print("\nTest lookups:")
        for pct in [14.5, 27.3, 43.0, 60.6, 74.1]:
            print(f"  {pct:5.1f}% -> {get_turn_name(zones, pct)}")
