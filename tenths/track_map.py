"""
Track Map Parser — Maps telemetry percentages to turn names.
==============================================================
Reads track reference files from Sim/tracks/<track>.md and provides
a lookup function to convert track percentages to turn names.

Usage:
    from track_map import load_track_map, get_turn_name
    track = load_track_map('fuji_nochicane')
    name = get_turn_name(track, 14.5)  # → 'T1-T2 TGR Corner'
"""

import os
import re

# Where track map files live
# Try multiple locations — the workspace has both the Sim repo and telemetry folder
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_TELEMETRY_ROOT = os.path.dirname(_SCRIPT_DIR)
TRACK_MAPS_DIRS = [
    os.path.join(os.path.dirname(_TELEMETRY_ROOT), "Sim", "Sim", "tracks"),  # from telemetry junction
    os.path.join(_TELEMETRY_ROOT, "..", "Sim", "Sim", "tracks"),  # relative fallback
    r"c:\Users\justi\Documents\Sim\Sim\tracks",  # absolute fallback
]


def load_track_map(venue_name):
    """
    Load a track map from Sim/tracks/<venue>.md.
    Returns a list of turn zones, or empty list if file not found.

    Each zone: {'pct_center': float, 'pct_range': (min, max), 'turn': str, 'name': str, 'full': str}
    """
    # Find the tracks directory
    tracks_dir = None
    for d in TRACK_MAPS_DIRS:
        if os.path.isdir(d):
            tracks_dir = d
            break
    if not tracks_dir:
        return []

    # Try exact match first, then fuzzy
    candidates = [
        os.path.join(tracks_dir, f"{venue_name}.md"),
        os.path.join(tracks_dir, f"{venue_name.replace(' ', '_')}.md"),
    ]

    # Also try partial matches
    for f in os.listdir(tracks_dir):
        if venue_name.lower().replace(' ', '') in f.lower().replace('_', '').replace(' ', ''):
            candidates.append(os.path.join(tracks_dir, f))

    filepath = None
    for c in candidates:
        if os.path.exists(c):
            filepath = c
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
            'turn': turn,
            'name': name if name != '—' else '',
            'full': full_name,
        })

    return zones


def get_turn_name(track_map, pct, tolerance=4.0):
    """
    Given a track percentage, return the closest turn name.
    Returns the full turn name (e.g., 'T1-T2 TGR Corner') or a fallback with percentage.

    Args:
        track_map: list from load_track_map()
        pct: track position percentage (0-100)
        tolerance: max distance in % to consider a match (default 4%)
    """
    if not track_map:
        return f"({pct:.1f}%)"

    best_match = None
    best_dist = tolerance + 1

    for zone in track_map:
        # Check if pct falls within the zone's range (with tolerance)
        low = zone['pct_range'][0] - tolerance
        high = zone['pct_range'][1] + tolerance

        if low <= pct <= high:
            # Distance to center
            dist = abs(pct - zone['pct_center'])
            if dist < best_dist:
                best_dist = dist
                best_match = zone

    if best_match:
        return best_match['full']
    return f"({pct:.1f}%)"


def get_turn_short(track_map, pct, tolerance=4.0):
    """Like get_turn_name but returns just the turn number (e.g., 'T1-T2')."""
    if not track_map:
        return f"{pct:.1f}%"

    best_match = None
    best_dist = tolerance + 1

    for zone in track_map:
        low = zone['pct_range'][0] - tolerance
        high = zone['pct_range'][1] + tolerance
        if low <= pct <= high:
            dist = abs(pct - zone['pct_center'])
            if dist < best_dist:
                best_dist = dist
                best_match = zone

    if best_match:
        return best_match['turn']
    return f"{pct:.1f}%"


if __name__ == "__main__":
    # Test
    import sys
    track_name = sys.argv[1] if len(sys.argv) > 1 else "fuji_nochicane"
    zones = load_track_map(track_name)
    if not zones:
        print(f"No track map found for '{track_name}'")
        print(f"Searched in: {TRACK_MAPS_DIRS}")
    else:
        print(f"Track map: {track_name} ({len(zones)} zones)")
        for z in zones:
            print(f"  {z['pct_range'][0]:>3}-{z['pct_range'][1]:>3}%  {z['full']}")
        # Test lookups
        print("\nTest lookups:")
        for pct in [14.5, 27.3, 43.0, 60.6, 74.1]:
            print(f"  {pct:.1f}% → {get_turn_name(zones, pct)}")
