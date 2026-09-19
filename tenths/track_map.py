"""
Track Map Parser — Maps telemetry percentages to turn names.
==============================================================
Primary source: bundled trackLandmarksData.json (457 iRacing tracks with
corner positions in meters, from CrewChief community data).

Corner-distance repairs: bundled track_corner_overrides.json patches a handful
of corrupt corner *distance* records in the community file (reversed/garbage
`end`) so the affected corner is labelled at its correct location instead of
being dropped. Turn numbers are NOT changed by overrides — they come from the
community file and are already iRacing-standard. iRacing publishes no per-corner
turn *positions* in any API or SDK (only a turn *count*), so this repair is done
at build time, offline; see `docs/IRACING_TRACK_API_INVESTIGATION.md` and
`tools/build_track_corner_overrides.py`.

Fallback: hand-tuned tracks/*.md files (legacy, used when landmark data
doesn't cover a track).

Usage:
    from track_map import load_track_map, get_turn_name
    track = load_track_map('roadatlanta_full')           # slug match
    track = load_track_map('winton_national', track_id=439)  # TrackID-keyed
    name = get_turn_name(track, 83.0)  # → 'T10'

`track_id` (iRacing's canonical WeekendInfo.TrackID, available as
`session_info['track_id']`) is the exact identity to key overrides on; the slug
path remains as a fallback for tracks no override references or whose id is
unknown.
"""

import os
import re
import sys
import json

from tenths.applog import get_logger

log = get_logger(__name__)

# Fuzzy-match tolerance for get_turn_name, expressed as a DISTANCE rather than a
# lap percentage. A pure percentage means wildly different distances per track —
# 5% is 946 m at the Nordschleife but 21 m at a bullring — which is how a "no
# match" becomes a confidently wrong neighbour's name. 150 m is roughly where
# late braking still belongs to the corner ahead (about 3% of a lap at COTA).
DEFAULT_TOLERANCE_M = 150.0
# Ceiling on the converted tolerance, and the tolerance used for .md maps that
# carry no track length. A pure metre tolerance overcorrects on very short
# tracks: 150 m is 76% of a lap at `iowa legends` (198 m), which would name a
# corner from three-quarters of a lap away. Half the tracks in the bundled data
# are under 3 km, where 150 m is looser than the 5% they were matched with
# before. _tolerance_pct therefore takes the TIGHTER of the two, so the metre
# rule only ever tightens matching and can never regress a short track.
DEFAULT_TOLERANCE_PCT = 5.0
# `approximateTrackLength` is approximate, so a corner may legitimately end a
# metre or two past it. Overruns within this fraction are clamped to the line;
# anything beyond is treated as corrupt. See _load_from_landmarks.
_LENGTH_GRACE_FRACTION = 0.01


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
def _user_tracks_dir():
    """Where auto-generated maps are written; also searched on read.

    Imported lazily so track_map does not depend on config at module scope.
    """
    try:
        from tenths.config import USER_TRACKS_DIR
        return USER_TRACKS_DIR
    except Exception:
        return ''


TRACK_MAPS_DIRS = [
    os.environ.get('TENTHS_TRACKS_DIR', ''),        # explicit override wins
    _user_tracks_dir(),                             # user's generated maps
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

# Bundled corner-distance override data — repairs corrupt records in the
# community landmark file. Same frozen/source candidate handling as landmarks.
_OVERRIDES_CANDIDATES = [
    os.path.join(_RESOURCE_BASE, "data", "track_corner_overrides.json"),  # frozen
    os.path.join(_SCRIPT_DIR, "data", "track_corner_overrides.json"),     # source
]
_OVERRIDES_PATH = next((p for p in _OVERRIDES_CANDIDATES if os.path.exists(p)), _OVERRIDES_CANDIDATES[-1])
_overrides_cache = None  # {'by_slug': {slug: [corrections]}, 'by_id': {id: [corrections]}}


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


def _load_overrides():
    """Load the bundled corner-distance overrides (cached after first call).

    Returns a dict with two indexes:
        {'by_slug': {slug: [correction, ...]},
         'by_id':   {track_id: [correction, ...]}}
    Absent or malformed file degrades to empty indexes — overrides are an
    enhancement, never a hard dependency, so a missing artifact must behave
    exactly like today (validator drops the corrupt corner).
    """
    global _overrides_cache
    if _overrides_cache is not None:
        return _overrides_cache

    empty = {'by_slug': {}, 'by_id': {}}
    if not os.path.exists(_OVERRIDES_PATH):
        _overrides_cache = empty
        return _overrides_cache

    try:
        with open(_OVERRIDES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("Could not read corner overrides %s: %s; ignoring.",
                    _OVERRIDES_PATH, exc)
        _overrides_cache = empty
        return _overrides_cache

    by_slug = {}
    by_id = {}
    for track in data.get('tracks', []):
        corrections = track.get('corrections') or []
        if not corrections:
            continue
        slug = track.get('slug')
        if slug:
            by_slug[slug] = corrections
        tid = track.get('track_id')
        if tid is not None:
            by_id[tid] = corrections
    _overrides_cache = {'by_slug': by_slug, 'by_id': by_id}
    return _overrides_cache


def _corrections_for(lookup_key, track_id):
    """Return the correction list for a track, TrackID first then slug.

    TrackID is iRacing's canonical identity; prefer it so a slug rename upstream
    cannot silently detach a repair from its track. Fall back to the slug for
    tracks whose id is unknown (track_id is None in the artifact).
    """
    overrides = _load_overrides()
    if track_id is not None and track_id in overrides['by_id']:
        return overrides['by_id'][track_id]
    return overrides['by_slug'].get(lookup_key, [])


def _apply_corner_overrides(landmarks, corrections):
    """Return a new landmark list with corrections applied by matching names.

    A correction repairs a corner's distance pair (`set_range`) or explicitly
    keeps it dropped (`drop`). Matching is by the exact landmarkNames list, which
    is stable within a track. Applied BEFORE validation so a repaired record then
    passes the same range/length checks as any other — a bad override cannot
    bypass the guards in _load_from_landmarks.
    """
    if not corrections:
        return landmarks

    # Index corrections by a hashable form of their names list.
    by_names = {tuple(c.get('names') or []): c for c in corrections}
    patched = []
    for lm in landmarks:
        key = tuple(lm.get('landmarkNames') or [])
        correction = by_names.get(key)
        if not correction:
            patched.append(lm)
            continue
        action = correction.get('action')
        if action == 'set_range':
            repaired = dict(lm)
            repaired['distanceRoundLapStart'] = correction['start']
            repaired['distanceRoundLapEnd'] = correction['end']
            log.debug("Applied corner override to %s: (%s -> %s)",
                      key, correction['start'], correction['end'])
            patched.append(repaired)
        elif action == 'drop':
            # Leave the record as-is; the validator will drop it. Recorded here
            # so the intent is explicit rather than incidental.
            log.debug("Corner override marks %s unrecoverable; leaving dropped.",
                      key)
            patched.append(lm)
        else:
            patched.append(lm)
    return patched


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


def _load_from_landmarks(venue_slug, track_id=None):
    """Load track zones from bundled landmark data.

    Args:
        venue_slug: iRacing track slug from .ibt filename (e.g., 'roadatlanta_full')
        track_id: iRacing canonical TrackID (session_info['track_id']), used to
            key corner-distance overrides. Optional; the slug is used as a
            fallback match key when it is None or unknown.

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

    # Repair corrupt corner distances BEFORE validation. A repaired corner then
    # runs the same range/length/uniqueness guards below as any other, so an
    # override cannot bypass them — it only turns a would-be-dropped corner into
    # a valid one. See _apply_corner_overrides and the investigation doc.
    raw_landmarks = _apply_corner_overrides(
        entry.get('trackLandmarks', []),
        _corrections_for(lookup_key, track_id))

    zones = []
    for landmark in raw_landmarks:
        dist_start = landmark.get('distanceRoundLapStart', 0)
        dist_end = landmark.get('distanceRoundLapEnd', 0)
        names = landmark.get('landmarkNames', [])

        turn_label, friendly_name, full_name = _format_landmark_name(names)

        # Validate the raw record BEFORE it can reach the report. The landmark
        # file is CrewChief's community-maintained data and carries a handful of
        # corrupt corners (e.g. barcelona gp T9 = 2800->2005 m). A corner whose
        # end precedes its start produces a reversed pct_range that the phase-1
        # `low <= pct <= high` test can never satisfy, so get_turn_name falls
        # back to the nearest neighbour and labels the stretch with the WRONG
        # turn — a wrong name is worse than an absent one. A dropped corner
        # degrades to a "(43.8%)" fallback, which the report already renders.
        # A future data refresh could reintroduce bad records with no other
        # signal, so this guard is permanent, not a one-off cleanup; the paired
        # test asserts against the production file.
        if dist_end <= dist_start:
            log.warning(
                "Dropping corrupt landmark %s on %r: end %.0fm <= start %.0fm",
                full_name, lookup_key, dist_end, dist_start)
            continue
        if dist_end > track_length * (1 + _LENGTH_GRACE_FRACTION):
            log.warning(
                "Dropping corrupt landmark %s on %r: end %.0fm exceeds track "
                "length %.0fm", full_name, lookup_key, dist_end, track_length)
            continue
        if dist_end > track_length:
            # Only just past the line. `approximateTrackLength` is approximate —
            # measured against real telemetry it is out by up to ~0.02% — so a
            # corner ending a metre or two "past" the lap is a real corner, not
            # corruption. Two ship in the data today: nordschleife T13 (+1 m) and
            # virginia 2022 patriot T1 (+2 m). Clamp to the line rather than
            # dropping, so a valid corner is never lost and pct_range stays
            # inside 0-100.
            log.debug(
                "Clamping landmark %s on %r: end %.0fm just past track length "
                "%.0fm", full_name, lookup_key, dist_end, track_length)
            dist_end = track_length

        # Convert distance to percentage
        pct_start = (dist_start / track_length) * 100
        pct_end = (dist_end / track_length) * 100
        pct_center = (pct_start + pct_end) / 2

        zones.append({
            'pct_center': pct_center,
            'pct_range': (pct_start, pct_end),
            'dist_range': (dist_start, dist_end),
            'track_length_m': track_length,
            'turn': turn_label,
            'name': friendly_name,
            'full': full_name,
        })

    _ensure_unique_full_names(zones)
    return zones


def _ensure_unique_full_names(zones):
    """Make each zone's `full` name unique within the track, in place.

    report.py joins telemetry to corners on the `full`/`turn_name` string with
    `.find()`, which silently takes the first match — so two zones sharing a
    name would show one zone's data under both corners. Suffix any collision
    with its lap percentage, which is always distinct, rather than reordering or
    dropping. Turn order is preserved; only genuinely duplicated names change.
    """
    seen = {}
    for zone in zones:
        name = zone['full']
        if name in seen:
            disambiguated = f"{name} ({zone['pct_center']:.0f}%)"
            log.warning(
                "Duplicate turn name %r on a track; renaming to %r so report "
                "joins do not collide", name, disambiguated)
            zone['full'] = disambiguated
        else:
            seen[name] = True


def load_track_map(venue_name, track_id=None):
    """
    Load a track map for the given venue.

    Lookup order:
    1. Bundled trackLandmarksData.json (457 tracks, exact slug match), with
       corrupt corner distances repaired from track_corner_overrides.json.
    2. Hand-tuned tracks/*.md files (legacy fallback)

    Args:
        venue_name: iRacing track slug (e.g. 'barcelona_gp'). Callers that have
            parsed the .ibt should pass the slug from session_info
            ('track_name_internal') or the .ibt filename.
        track_id: iRacing canonical TrackID (session_info['track_id']). When
            supplied, corner-distance overrides are matched on it first, falling
            back to the slug. Optional and backward-compatible — omitting it
            keeps the slug-only behaviour.

    Returns a list of turn zones, or empty list if not found.
    Each zone: {
        'pct_center': float,          # midpoint of the zone as track %
        'pct_range': (start, end),    # zone span as track %
        'dist_range': (start, end) | None,  # zone span in meters (landmarks only)
        'track_length_m': float,      # landmarks only; used by the metre tolerance
        'turn': str,                  # short label, e.g. 'T5'
        'name': str,                  # friendly name, e.g. 'Canada Corner' (may be '')
        'full': str,                  # combined, e.g. 'T5 Canada Corner'
    }
    """
    # 1. Try bundled landmark data first (primary source)
    zones = _load_from_landmarks(venue_name, track_id=track_id)
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


def _tolerance_pct(track_map, tolerance_m):
    """Convert a metre tolerance to a lap-percentage for this track.

    Landmark zones carry `track_length_m`, so the same physical distance means
    the same thing on every track. Legacy .md maps carry no length, so there is
    nothing to convert against — fall back to the fixed percentage tolerance
    those maps were always matched with.

    The result is capped at DEFAULT_TOLERANCE_PCT: on a very short oval the
    metre tolerance would otherwise cover most of the lap. Taking the tighter of
    the two means this rule only ever narrows matching relative to the old
    behaviour, never widens it.
    """
    length = None
    for zone in track_map:
        length = zone.get('track_length_m')
        if length:
            break
    if length and length > 0:
        return min((tolerance_m / length) * 100.0, DEFAULT_TOLERANCE_PCT)
    return DEFAULT_TOLERANCE_PCT


def _closest_within(track_map, pct, tol_pct):
    """Return the zone whose center is nearest pct within tol_pct, or None."""
    best_match = None
    best_dist = tol_pct + 1
    for zone in track_map:
        dist = abs(pct - zone['pct_center'])
        if dist < best_dist:
            best_dist = dist
            best_match = zone
    if best_match and best_dist <= tol_pct:
        return best_match
    return None


def get_turn_name(track_map, pct, tolerance_m=DEFAULT_TOLERANCE_M):
    """
    Given a track percentage, return the closest turn name.
    Returns the full turn name (e.g., 'T1-T2 TGR Corner') or a fallback with percentage.

    Matching strategy:
    1. If pct falls within any zone's defined range → use that zone (exact match)
    2. Otherwise, find the closest zone center within tolerance (fuzzy fallback)

    Args:
        track_map: list from load_track_map()
        pct: track position percentage (0-100)
        tolerance_m: max distance IN METRES to consider a fuzzy match. A metre
            tolerance behaves the same on a 400 m oval and the 18.9 km
            Nordschleife; a percentage tolerance did not. For .md maps that
            carry no track length it degrades to DEFAULT_TOLERANCE_PCT.
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
    # Braking typically happens a short distance before a corner.
    match = _closest_within(track_map, pct, _tolerance_pct(track_map, tolerance_m))
    return match['full'] if match else f"({pct:.1f}%)"


def get_turn_short(track_map, pct, tolerance_m=DEFAULT_TOLERANCE_M):
    """Like get_turn_name but returns just the turn number (e.g., 'T1-T2')."""
    if not track_map:
        return f"{pct:.1f}%"

    # Phase 1: exact range match
    for zone in track_map:
        if zone['pct_range'][0] <= pct <= zone['pct_range'][1]:
            return zone['turn']

    # Phase 2: closest center within tolerance
    match = _closest_within(track_map, pct, _tolerance_pct(track_map, tolerance_m))
    return match['turn'] if match else f"{pct:.1f}%"


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
