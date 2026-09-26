# Corner / Turn Data — Current State and Next Steps

**Written 2026-09-03. This is a live work queue, not a historical document.**
**Status 2026-09-25:** all three pieces of work below are committed — #1 and #2
together in `bae586f`, the detection prototype (#3) in `405fc6a`. The review
fixes listed under "Review findings" were NOT applied; they are still open.

Related documents:
- `docs/IRACING_TRACK_API_INVESTIGATION.md` — why the iRacing API cannot supply
  corner positions. That finding is settled; do not re-investigate it.
- `docs/POST_MVP.md` — Track Data Integrity (resolved), Track Sections (unblocked).
- `docs/TECH_DEBT.md` — TM1/TM2 track-map issues.

---

## Why this work exists

Coaching is addressed by turn number: "brake later for T5", "get to throttle
sooner through T3". The turn number is the *address* the driver acts on. A wrong
number sends the driver to the wrong corner and destroys trust in the tool. So
correct, iRacing-standard turn numbering is a **correctness requirement**, not
cosmetic polish.

The current source, `tenths/data/trackLandmarksData.json`, is an enriched
derivative of CrewChief's community landmark data. It is unreliable in two ways:
four tracks have corrupt corner distances, and — the bigger finding — **its turn
count disagrees with iRacing's own count on 6 of the 10 track configs measured**
(see the table below).

---

## What was committed (formerly "Uncommitted state")

- **Track Data Integrity** (load-time validation in `tenths/track_map.py`,
  `tests/test_track_data_integrity.py`) and **corner-distance overrides**
  (`tools/build_track_corner_overrides.py`, `tenths/data/track_corner_overrides.json`,
  `tests/test_track_corner_overrides.py`, `track_id` threaded into
  `load_track_map`) — commit `bae586f`, as one commit rather than the two this
  document suggested.
- **Corner detection prototype** (`tools/detect_corners.py`) — commit `405fc6a`.
  Still investigation only; not wired into production.

## Review findings on the override work (#2) that still need action

Checked 2026-09-25: none of these four has been applied yet.

1. **`docs/IRACING_TRACK_API_INVESTIGATION.md` overclaims Martinsville.** It says
   T3 is "fully recovered (a clean transposition)". The swap produces
   `474 -> 481` — a **7 m** corner that **overlaps T4** (`475 -> 677`). Its
   neighbours span 92 m, 94 m and 202 m, so a 7 m corner is physically
   implausible: the source record is probably corrupt in a further way a swap
   cannot fix. The repair is defensible (both numbers came from the data; inventing
   `350-470` would be worse) but the wording is not. Fix the claim, or reclassify
   Martinsville T3 as unrecoverable.
2. **No overlap validation exists anywhere.** Validation catches reversed and
   out-of-bounds ranges but not overlapping zones, which make phase-1 matching in
   `get_turn_name` order-dependent (first match in list order wins). Overlaps are
   pre-existing in the source data (e.g. Bathurst `skyline` 3280-3360 and
   `the_esses` 3280-3380), so this is not newly introduced — but add a guard test.
3. **`track_id` keying is currently dead code.** All four artifact entries have
   `track_id: null`, so every match falls through to the slug path. ~30 lines
   threaded through 6 files for zero present effect. Defensible future-proofing
   (the generator has a `--session` backfill), but the doc should say so plainly
   rather than describing it as the active mechanism. **Backfilling the four IDs
   is easy now** — see the ID table below.
4. Minor: unfinished date string in the investigation doc — "retired on 2026-…
   (Dec 9, 2025)".

Verified good and needing no action: override-before-validation ordering holds and
both bypass tests genuinely inject bad overrides and assert the corner is still
dropped; turn numbers are structurally incapable of being altered (`names` is only
a match selector); graceful degradation is covered; `installer/tenths.spec:45`
already bundles the whole `tenths/data` dir so the artifact ships automatically.

---

## The detection prototype (#3) — measured results

`tools/detect_corners.py` derives corner positions from your own telemetry and
anchors the corner **count** to `track_num_turns` from the `.ibt` header, which is
iRacing's own authoritative number. No API, no account, no network, nothing
hand-entered.

Algorithm: smooth `|LatAccel|`, take local maxima as apexes, suppress apexes
closer than `DEFAULT_SEP_M`, then merge **same-direction** neighbours until the
count equals `track_num_turns`; corner spans come from walking out to
`BOUND_FRACTION` of the apex load; positions are the median across clean laps.

Scoring is **one-to-one** against the bundled map — each known corner may be
claimed by at most one detection. (Nearest-neighbour scoring badly flattered an
earlier version: three detections collapsing onto one known corner counted as
three "matches".)

| track | iRacing turns | known zones | one-to-one matched | rate |
|---|---|---|---|---|
| Coronado | 16 | 18 | 15 | 94% |
| Mid-Ohio Full | 13 | 11 | 10 | 91% |
| COTA GP | 20 | 20 | 18 | 90% |
| Tsukuba 2k Full | 9 | 9 | 8 | 89% |
| Oran Park GP | 12 | 9 | 8 | 89% |
| VIR Full | 18 | 16 | 14 | 88% |
| Barber Full | 16 | 16 | 13 | 81% |
| Watkins Glen Classic Boot | 11 | 11 | 8 | 73% |
| Sonoma Sports Car | 12 | 13 | 8 | 62% |
| Oschersleben B | 8 | 5 | 0 | — |

On matched corners, positional agreement is **sub-1% of lap** (COTA T11 detected
46.68% vs known 46.8%; T12 68.82% vs 68.9%) — better precision than the community
file's hand-entered distances.

### Approaches already tried — do not repeat these

| version | approach | result |
|---|---|---|
| v1 | threshold `|LatAccel|` into cornering regions | **Failed.** 3 of 16 at Barber. The car never unloads between consecutive corners, so T1-T4 merged into one 660 m region. A level threshold cannot separate corners that flow into one another. |
| v2 | hand-rolled prominence walk | Double-counted corners (Barber T1 found twice, 52 m apart) while missing T3-T5 entirely. |
| v3 | greedy top-N by peak height | 54 total matches. Loses gentle-but-real corners. |
| v4 | merge nearest adjacent pair down to N | **Worse (52).** Destroyed COTA's alternating esses. |
| v5 | merge **same-direction** neighbours only | **Best (55).** An L→R transition is always two separate corners. Current state. |

---

## Next steps, in priority order

### 1. ~~Commit the stacked work~~ — done (`bae586f`, `405fc6a`)
Apply the four open review findings above instead.

### 2. Backfill the four `track_id` values (15 min)
This removes finding #3 and makes the TrackID path actually live. The IDs are
already known from the local archive and from iRacing's Track Info dialog
("Track No."). Confirmed IDs from `parse_session_info` over the archive:

| slug | TrackID | iRacing turns |
|---|---|---|
| barber 2026 | 585 | 16 |
| coronado | 589 | 16 |
| cota gp | 229 | 20 |
| midohio full | 153 | 13 |
| oran gp | 202 | 12 |
| oschersleben bcourse | 455 | 8 |
| sonoma 2025 sportscar | 570 | 12 |
| tsukuba 2kfull | 324 | 9 |
| virginia 2022 full | 465 | 18 |
| watkinsglen 2021 fullnoloop | 435 | 11 |

None of the four override tracks (barcelona gp, aragon gp, aragon moto,
martinsville) are in the local archive, so their IDs must come from the iRacing UI
(Track Info → "Track No.") or a session at that track. **Do not guess them.**

### 3. Improve detection: confidence filter + stop forcing N (2-3 h)
The two known weaknesses, both visible in the data:
- **Use the per-corner lap count as a confidence signal.** Real corners appear on
  8-14 laps; noise appears on 1-3. Every spurious detection in the current output
  (COTA T1 at 0.39 G, VIR T14 at 0.33 G, Watkins Glen T5/T6/T8) has a low lap
  count. Reject corners seen on fewer than ~50% of clean laps.
- **Stop forcing exactly `track_num_turns`.** When a long multi-apex corner
  over-merges (the Watkins Glen Loop collapsed into a single 1470 m span), the
  algorithm pads up to N with low-G noise — that is why Watkins Glen regressed
  from 9 to 8. Instead, report the count it is confident about, and flag the
  difference from `track_num_turns` as "needs review".

Re-measure against the table above after each change. Expect the weak tracks
(Sonoma, Watkins Glen, Barber) to improve.

### 4. Decide the target architecture (needs owner input)
Detection gives **numbers and positions**. It does not give **names**
("Charlotte's Web", "The Esses"), which only exist in human sources. Options:
- **Hybrid (recommended):** telemetry-derived positions + `track_num_turns` for
  the count, with a small curated per-track file supplying names and resolving
  ambiguities. Keeps the community file as fallback for tracks never driven.
- **Detection only:** ship `T1..TN` with no names. Simpler, less friendly.
- **Keep the community file primary**, using detection only to validate it and
  flag disagreements. Lowest risk, keeps the known-bad data.

Note the community file cannot be trusted on count: **6 of 10 configs disagree
with iRacing's own turn count** (Oran 9 vs 12, Mid-Ohio 11 vs 13, VIR 16 vs 18,
Oschersleben 5 vs 8, Coronado 18 vs 16, Sonoma 13 vs 12). Oschersleben's 0/5 score
is most likely bad *known* data, not bad detection.

### 5. Where screenshots fit (owner task, ~10 min per track)
iRacing's Track Info → Track Map dialog shows the official numbered layout and the
"Track No." (TrackID). **Do not use these for bulk data entry** — the count and
TrackID are already in every `.ibt`, and the screenshot has no lap-distance
information, which is the only thing actually missing. Use them for:
- **Convention edge cases:** is a chicane one turn or two? Sonoma's T3A sub-turn?
- **Real corner names**, which make coaching read far better than "T7".
- **Visual verification** that detected corners match the official layout.

Scope is small: the archive covers **10 track configs**, not 457.

---

## Do not redo

- **Do not re-investigate the iRacing API for corner positions.** Settled:
  `track/get` returns `corners_per_lap` (a count), `track/assets` returns
  `track_map_layers.turns` (a rendered SVG image). Neither has positions. See
  `docs/IRACING_TRACK_API_INVESTIGATION.md`.
- **Do not re-pull CrewChief upstream.** Checked: upstream has 37 iRacing tracks
  vs our 457, uses `landmarkName` (singular, descriptive only — **no turn
  numbers**), and still contains the same reversed Barcelona T9 record. A refresh
  would regress coverage and fix nothing.
- **Do not look for an external turn-number database.** Checked
  `bacinger/f1-circuits` (fetched Barcelona: outline polyline plus name/length/
  altitude, zero turn markers), `TUMFTM/racetrack-database` and
  `f1tenth_racetracks` (centerlines/racing lines, ~20-25 mostly-F1 tracks, no
  labels), and OpenStreetMap (raceway geometry, inconsistent corner naming).
  Geometry is freely available; turn **labels** are not, in any structured form.
- **Do not use a lateral-G threshold to segment corners** (v1 above).
- **Do not merge adjacent apexes by proximity alone** (v4 above).
