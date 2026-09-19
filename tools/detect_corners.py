"""PROTOTYPE: derive corner positions from telemetry, anchored to iRacing's own
turn count (`track_num_turns`) from the .ibt header.

History of this prototype, kept because each failure is informative:

  v1  Thresholded |LatAccel| into "cornering regions". Failed: on a twisty track
      the car never unloads between consecutive corners, so Barber T1-T4 merged
      into one 660 m region — 3 of 16 corners found. A level threshold cannot
      separate corners that flow into one another.
  v2  Apex-first with a hand-rolled prominence walk. Better (34 candidates) but
      double-counted: two apexes inside one corner were kept as two corners
      (Barber T1 detected twice, 52 m apart) while T3-T5 were missed entirely.
      The prominence walk was convoluted and scored real corners as flat.
  v3  (this) Simplest thing that can work: smooth, take local maxima, then
      greedily select the strongest apexes subject to a minimum separation.
      Separation does the corner-merging work that prominence did badly.

Scoring is ONE-TO-ONE against the known map: each known corner may be claimed by
at most one detected corner. Nearest-neighbour scoring flattered v2 badly — three
detections collapsing onto one known corner counted as three "matches".

Investigation tool, not production.
  python tools/detect_corners.py            # all tracks, default separation
  python tools/detect_corners.py --sweep    # calibrate separation on Barber+COTA
"""
import contextlib
import glob
import io
import os
import sys

import numpy as np

from tenths.analyzer import parse_ibt, get_valid_laps, parse_session_info
from tenths.track_map import load_track_map

SMOOTH_S = 0.15          # smoothing window, seconds
MIN_APEX_G = 0.30        # ignore apexes below this lateral load
BOUND_FRACTION = 0.55    # corner span: walk out to this fraction of apex G
# Minimum distance between two distinct apexes. Calibrated by sweeping 60-180 m
# against the known maps for Barber, COTA, Mid-Ohio and VIR: 60 m scored best
# overall (13/16, 18/20, 10/11, 14/16) once same-direction-only merging was in
# place. Larger values start merging genuinely separate corners.
DEFAULT_SEP_M = 60.0
MATCH_TOL_PCT = 3.0      # a detection "matches" a known corner within this


def _smooth(a, win):
    if win < 3:
        return a
    return np.convolve(a, np.ones(win) / win, mode='same')


def _lap_corners(lap, sample_rate, n_turns, sep_m):
    sig_raw = lap['LatAccel'].abs().to_numpy()
    signed = lap['LatAccel'].to_numpy()
    dist = lap['LapDist'].to_numpy()
    sig = _smooth(sig_raw, max(3, int(SMOOTH_S * sample_rate)))
    n = len(sig)

    peaks = [i for i in range(1, n - 1)
             if sig[i] >= sig[i - 1] and sig[i] > sig[i + 1] and sig[i] >= MIN_APEX_G]
    if not peaks:
        return []

    # First pass: suppress apexes closer than sep_m, keeping the stronger. This
    # removes 60 Hz double-tops within a single apex.
    peaks.sort(key=lambda i: -sig[i])
    kept = []
    for i in peaks:
        if all(abs(dist[i] - dist[j]) >= sep_m for j in kept):
            kept.append(i)
    kept.sort(key=lambda i: dist[i])

    # Build spans for every surviving candidate.
    cands = []
    for i in kept:
        thresh = sig[i] * BOUND_FRACTION
        j = i
        while j > 0 and sig[j] > thresh:
            j -= 1
        k = i
        while k < n - 1 and sig[k] > thresh:
            k += 1
        cands.append({'apex_m': float(dist[i]), 'start': float(dist[j]),
                      'end': float(dist[k]), 'peak_g': float(sig[i]),
                      'dir': 'L' if signed[i] > 0 else 'R'})

    # Second pass: AGGLOMERATE down to exactly n_turns by repeatedly merging the
    # closest ADJACENT pair. Greedily dropping the weakest apexes instead (v3)
    # lost gentle-but-real corners like Barber T5 while keeping both apexes of a
    # long corner like the Watkins Glen Loop. Merging fixes both failure modes at
    # once: a multi-apex corner collapses into one numbered turn, and a low-G
    # kink survives because it is far from its neighbours.
    # Only SAME-DIRECTION neighbours may merge. A left-then-right transition is
    # always two separate numbered corners, so merging by proximity alone
    # destroyed real corners (COTA's alternating esses went 19->17 matches).
    # Two same-direction apexes close together are far more likely to be two
    # apexes of one corner (Barber's back section, the Watkins Glen Loop).
    while len(cands) > n_turns:
        pairs = [(cands[i + 1]['apex_m'] - cands[i]['apex_m'], i)
                 for i in range(len(cands) - 1)
                 if cands[i]['dir'] == cands[i + 1]['dir']]
        if not pairs:
            # No same-direction pair left to merge; drop the weakest apex.
            weakest = min(range(len(cands)), key=lambda i: cands[i]['peak_g'])
            del cands[weakest]
            continue
        _, i = min(pairs, key=lambda g: g[0])
        a, b = cands[i], cands[i + 1]
        stronger = a if a['peak_g'] >= b['peak_g'] else b
        cands[i] = {
            'apex_m': stronger['apex_m'],
            'start': min(a['start'], b['start']),
            'end': max(a['end'], b['end']),
            'peak_g': max(a['peak_g'], b['peak_g']),
            'dir': stronger['dir'],
        }
        del cands[i + 1]
    return cands


def detect(path, sep_m=DEFAULT_SEP_M):
    df, sample_rate, vehicle, venue = parse_ibt(path)
    si = parse_session_info(path)
    n_turns = si.get('track_num_turns') or 0
    valid = get_valid_laps(df)
    if not len(valid) or not n_turns:
        return [], si

    per_lap = []
    for ln in valid:
        lap = df[df['Lap'] == ln]
        if len(lap) < 100:
            continue
        c = _lap_corners(lap, sample_rate, n_turns, sep_m)
        if c:
            per_lap.append(c)
    if not per_lap:
        return [], si

    counts = [len(c) for c in per_lap]
    modal = max(set(counts), key=counts.count)
    template = next(c for c in per_lap if len(c) == modal)

    merged = []
    for t in template:
        a, s, e, g = [], [], [], []
        for lapc in per_lap:
            best = min(lapc, key=lambda r: abs(r['apex_m'] - t['apex_m']))
            if abs(best['apex_m'] - t['apex_m']) <= sep_m:
                a.append(best['apex_m']); s.append(best['start'])
                e.append(best['end']); g.append(best['peak_g'])
        if a:
            merged.append({'apex_m': float(np.median(a)),
                           'start': float(np.median(s)),
                           'end': float(np.median(e)),
                           'peak_g': float(np.median(g)),
                           'dir': t['dir'], 'n_laps': len(a)})
    merged.sort(key=lambda c: c['apex_m'])
    for idx, c in enumerate(merged, start=1):
        c['turn'] = f"T{idx}"
    return merged, si


def _length_m(si):
    try:
        return float(str(si.get('track_length_km')).split()[0]) * 1000
    except Exception:
        return None


def score(detected, known, length_m):
    """One-to-one match count: each known corner claimed at most once."""
    if not known or not length_m:
        return 0, []
    unclaimed = list(known)
    pairs = []
    for c in detected:
        pct = c['apex_m'] / length_m * 100
        cands = [z for z in unclaimed if abs(z['pct_center'] - pct) <= MATCH_TOL_PCT]
        if cands:
            z = min(cands, key=lambda z: abs(z['pct_center'] - pct))
            unclaimed.remove(z)
            pairs.append((c['turn'], pct, z['full'], z['pct_center']))
        else:
            pairs.append((c['turn'], pct, None, None))
    return sum(1 for p in pairs if p[2]), pairs


def _sessions():
    arc = os.path.expanduser(r"~/Documents/iRacing/telemetry/_archive")
    seen = {}
    for f in sorted(glob.glob(os.path.join(arc, "*.ibt"))):
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                si = parse_session_info(f)
            except Exception:
                continue
        slug = (si.get('track_name_internal') or '').strip()
        if slug and slug not in seen:
            seen[slug] = f
    return seen


def sweep():
    out = ["Calibration sweep: one-to-one matches vs known map\n"]
    targets = ['barber 2026', 'cota gp', 'midohio full', 'virginia 2022 full']
    sess = _sessions()
    for sep in (60, 80, 100, 120, 150, 180):
        row = [f"sep={sep:4.0f}m: "]
        for slug in targets:
            f = sess.get(slug)
            if not f:
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    det, si = detect(f, sep_m=sep)
                except Exception:
                    row.append(f"{slug}=ERR ")
                    continue
            known = load_track_map(slug.replace(' ', '_'))
            L = _length_m(si)
            m, _ = score(det, known, L)
            row.append(f"{slug.split()[0]}: {m}/{len(known)} (det {len(det)}, "
                       f"iR {si.get('track_num_turns')})  ")
        out.append("".join(row))
    return "\n".join(out)


def report(slug_filter=None, sep_m=DEFAULT_SEP_M):
    out = []
    for slug, f in _sessions().items():
        if slug_filter and slug_filter not in slug:
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                det, si = detect(f, sep_m=sep_m)
            except Exception as exc:
                out.append(f"\n=== {slug}: ERROR {exc}")
                continue
        if not det:
            out.append(f"\n=== {slug}: no detection")
            continue
        known = load_track_map(slug.replace(' ', '_'))
        L = _length_m(si)
        m, pairs = score(det, known, L)
        out.append(f"\n=== {slug}: iRacing={si.get('track_num_turns')} turns, "
                   f"detected={len(det)}, known_zones={len(known)}, "
                   f"one-to-one matches={m}, len={L:.0f}m")
        out.append(f"  {'turn':>5} {'apex_m':>7} {'span':>13} {'pct':>6} "
                   f"{'G':>5} {'d':>2} {'laps':>4}  matched known")
        for c, p in zip(det, pairs):
            pct = c['apex_m'] / L * 100 if L else float('nan')
            mk = f"{p[2][:18]}@{p[3]:.1f}%" if p[2] else "-- none --"
            out.append(f"  {c['turn']:>5} {c['apex_m']:7.0f} "
                       f"{c['start']:6.0f}-{c['end']:<6.0f} {pct:6.2f} "
                       f"{c['peak_g']:5.2f} {c['dir']:>2} {c['n_laps']:4d}  {mk}")
    return "\n".join(out)


if __name__ == '__main__':
    if '--sweep' in sys.argv:
        txt = sweep()
    else:
        filt = next((a for a in sys.argv[1:] if not a.startswith('-')), None)
        txt = report(filt)
    with open("tools/detect_out.txt", "w", encoding="utf-8") as fh:
        fh.write(txt)
