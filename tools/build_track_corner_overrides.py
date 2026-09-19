"""
Build the track corner override artifact from the bundled landmark data.
===========================================================================
DEVELOPER TOOL — run manually, never in the end-user pipeline.

Why this exists
---------------
See `docs/IRACING_TRACK_API_INVESTIGATION.md` for the full reasoning. Summary:
iRacing publishes no per-corner turn *positions* anywhere a program can read
them — not in the `.ibt` header (only a turn *count*, `TrackNumTurns`), not in
the `/data/track/get` or `/data/track/assets` web API (a count plus a rendered
SVG image of the labels). So the corner spans Tenths needs cannot be "fetched".

The community file `tenths/data/trackLandmarksData.json` is the only broad source
of corner positions, and its turn *numbers* are already iRacing-standard and
correct. Its only defect is a handful of corrupt corner *distance* records with a
reversed or garbage `distanceRoundLapEnd`. The load-time validator in
`tenths/track_map.py` currently drops those, leaving the corner unlabelled. This
tool produces a small, reviewed **override artifact** that repairs the recoverable
ones so the corner is labelled at its correct location again.

What it does
------------
Scans every landmark entry for corner records the validator would reject
(`end <= start`, or `end` well beyond the track length) and classifies each:

- **transposition** — `start` sits AFTER the next corner's start, i.e. the pair
  is simply swapped. Fix: swap start/end. Fully recoverable.
- **corrupt_end** — `start` is in lap order (prev_end < start < next_start) but
  `end` is garbage. The true end is NOT recoverable from any authoritative
  source, so the corner is anchored as a short bounded zone starting at its
  known-good `start` and ending a conservative distance later, clamped below the
  next corner's start. Partially recoverable: correct location, bounded span.
- **unrecoverable** — neither the start nor a swap places the corner sensibly.
  Emitted with `action: "drop"` so the loader keeps dropping it (no worse than
  today), with the reason recorded.

The artifact is keyed on the iRacing track slug (`irTrackName`), which is the
authoritative match key the community file itself uses and which equals the
`.ibt` `WeekendInfo.TrackName`. Each record also carries a `track_id` field
(iRacing's canonical numeric id) when known — the loader prefers a `track_id`
match and falls back to the slug. `track_id` is left null for tracks no local
session has been seen for, rather than fabricated; fill it from a real `.ibt`
when one is available (see `--session` below).

Usage
-----
    python tools/build_track_corner_overrides.py            # rewrite artifact
    python tools/build_track_corner_overrides.py --check     # exit 1 if stale
    python tools/build_track_corner_overrides.py --session <file.ibt> [...]
        # backfill real track_id values from one or more .ibt files

The output (`tenths/data/track_corner_overrides.json`) is deterministic and
idempotent: re-running without new sessions produces byte-identical output.
"""

import argparse
import json
import os
import sys

# Allow running from the repo root without installing the package.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tenths.track_map import _LANDMARKS_PATH, _LENGTH_GRACE_FRACTION  # noqa: E402

OVERRIDES_PATH = os.path.join(
    _REPO_ROOT, "tenths", "data", "track_corner_overrides.json")

# A corrupt_end corner has no recoverable end. Anchor it as a short zone this
# many metres long, clamped below the next corner's start. Chosen small so the
# repaired zone never overlaps a neighbour; get_turn_name's nearest-centre
# fallback still reaches the surrounding stretch via DEFAULT_TOLERANCE_M.
_CORRUPT_END_SPAN_M = 60.0


def _is_corrupt(start, end, length):
    """Mirror the loader's reject rule exactly (see _load_from_landmarks)."""
    if end <= start:
        return True
    if end > length * (1 + _LENGTH_GRACE_FRACTION):
        return True
    return False


def _classify(idx, landmarks, length):
    """Classify one corrupt corner and return an override action dict.

    Uses only the neighbouring corners' known-good distances as evidence — no
    fabricated positions. `idx` is the corner's index within `landmarks`.
    """
    lm = landmarks[idx]
    start = lm.get('distanceRoundLapStart', 0)
    end = lm.get('distanceRoundLapEnd', 0)
    names = lm.get('landmarkNames') or []

    prev_end = landmarks[idx - 1].get('distanceRoundLapEnd', 0) if idx > 0 else 0
    next_start = (landmarks[idx + 1].get('distanceRoundLapStart', length)
                  if idx + 1 < len(landmarks) else length)

    # Transposition: the pair is simply swapped. Detectable because the recorded
    # start sits at or after the next corner's start, while the recorded end sits
    # in the correct window between the neighbours.
    if start >= next_start and prev_end < end < start:
        return {
            'names': names,
            'action': 'set_range',
            'start': end,
            'end': start,
            'reason': 'transposition — start/end were swapped; restored',
        }

    # Corrupt end: start is in lap order, end is garbage. Anchor a short bounded
    # zone at the trustworthy start; do NOT fabricate the true end.
    if prev_end < start < next_start:
        anchored_end = min(start + _CORRUPT_END_SPAN_M, next_start - 1)
        if anchored_end > start:
            return {
                'names': names,
                'action': 'set_range',
                'start': start,
                'end': anchored_end,
                'reason': ('corrupt end distance; start is in lap order so the '
                           'corner is anchored at its known-good start with a '
                           'bounded span (true end not recoverable)'),
            }

    # Neither the start nor a swap places it sensibly.
    return {
        'names': names,
        'action': 'drop',
        'reason': 'unrecoverable — start out of lap order and no valid swap',
    }


def build_overrides(session_track_ids=None):
    """Return the override artifact dict. Pure function of the landmark file
    (and any supplied slug->track_id backfill)."""
    session_track_ids = session_track_ids or {}
    with open(_LANDMARKS_PATH, encoding='utf-8') as f:
        raw = json.load(f)

    tracks = []
    for entry in raw.get('trackLandmarksData', []):
        slug = entry.get('irTrackName')
        length = entry.get('approximateTrackLength', 0)
        landmarks = entry.get('trackLandmarks') or []
        if not slug or not landmarks or length <= 0:
            continue

        corrections = []
        for i, lm in enumerate(landmarks):
            start = lm.get('distanceRoundLapStart', 0)
            end = lm.get('distanceRoundLapEnd', 0)
            if _is_corrupt(start, end, length):
                corrections.append(_classify(i, landmarks, length))

        if corrections:
            tracks.append({
                'slug': slug,
                'track_id': session_track_ids.get(slug),
                'approximateTrackLength': length,
                'corrections': corrections,
            })

    tracks.sort(key=lambda t: t['slug'])
    return {
        'schema_version': '1.0.0',
        'source': 'tenths/data/trackLandmarksData.json',
        'generated_by': 'tools/build_track_corner_overrides.py',
        'note': ('Build-time repairs for corrupt corner distance records in the '
                 'community landmark file. Turn numbers come from the community '
                 'file and are unchanged. See '
                 'docs/IRACING_TRACK_API_INVESTIGATION.md.'),
        'tracks': tracks,
    }


def _existing_track_ids():
    """Preserve any track_id values already backfilled into the artifact."""
    if not os.path.exists(OVERRIDES_PATH):
        return {}
    try:
        with open(OVERRIDES_PATH, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return {t['slug']: t['track_id'] for t in data.get('tracks', [])
            if t.get('track_id') is not None}


def _track_ids_from_sessions(paths):
    """Read slug->track_id from .ibt session files."""
    from tenths.analyzer import parse_session_info
    out = {}
    for p in paths:
        si = parse_session_info(p)
        slug = si.get('track_name_internal')
        tid = si.get('track_id')
        if slug and tid:
            out[slug] = tid
    return out


def _serialise(artifact):
    return json.dumps(artifact, indent=2, ensure_ascii=False) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='exit 1 if the artifact is out of date, do not write')
    parser.add_argument('--session', nargs='*', default=[],
                        help='.ibt files to backfill real track_id values from')
    args = parser.parse_args(argv)

    known = _existing_track_ids()
    known.update(_track_ids_from_sessions(args.session))

    artifact = build_overrides(known)
    text = _serialise(artifact)

    if args.check:
        current = ''
        if os.path.exists(OVERRIDES_PATH):
            with open(OVERRIDES_PATH, encoding='utf-8') as f:
                current = f.read()
        if current != text:
            print('track_corner_overrides.json is out of date; '
                  'run tools/build_track_corner_overrides.py', file=sys.stderr)
            return 1
        print('track_corner_overrides.json is up to date.')
        return 0

    os.makedirs(os.path.dirname(OVERRIDES_PATH), exist_ok=True)
    with open(OVERRIDES_PATH, 'w', encoding='utf-8') as f:
        f.write(text)

    n_tracks = len(artifact['tracks'])
    n_fixes = sum(len(t['corrections']) for t in artifact['tracks'])
    print(f'Wrote {OVERRIDES_PATH}')
    print(f'  {n_tracks} tracks, {n_fixes} corner corrections:')
    for t in artifact['tracks']:
        for c in t['corrections']:
            names = ','.join(c['names'])
            if c['action'] == 'set_range':
                print(f"    {t['slug']:20} {names:8} -> "
                      f"({c['start']}, {c['end']})  [{c['reason'].split(';')[0]}]")
            else:
                print(f"    {t['slug']:20} {names:8} -> drop  [{c['reason']}]")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
