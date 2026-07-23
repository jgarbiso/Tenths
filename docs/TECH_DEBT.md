# Technical Debt

Items identified during development that are acceptable for current use but should be addressed before production distribution.

---

## Watcher (`tenths/service/watcher.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| W1 | `_set_low_priority()` lowers entire process priority, not per-thread | Main loop also runs at below-normal during processing | Before adding tray UI in same process (Tier 3) |
| W2 | `_can_open_exclusive()` uses shared read, not true exclusive lock | Could theoretically trigger if iRacing allows read while still writing | If false triggers observed in production |
| W3 | No processing of pre-existing .ibt files on startup | Files present before watcher starts are missed | Tier 2 — add startup scan |
| W4 | `_processed` set grows unbounded | Negligible for typical sessions (1-5 per evening) | If watcher runs continuously for weeks |

## Analyzer (`tenths/analyzer.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| A1 | Braking zone detection only catches >50% brake pressure | Misses light-braking corners (e.g., 11 of 16 turns at Barber) | When iRacing API provides official turn positions (Phase 5) |
| A2 | Schema downgrade not prevented in migration system | If a newer Tenths version's JSON is opened by older version, it stamps the older schema | Before multi-user distribution |

## Report (`tenths/report.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| R1 | JS is embedded as Python string — no syntax validation at generation time | Stray brace can silently break all rendering | Consider extracting JS to a separate .js template file (Phase 2 dashboard) |
| R2 | Leaflet + Chart.js loaded from CDN | First load requires internet; subsequent loads cached | Bundle locally if packaging as offline installer (Tier 3) |

## Process (`tenths/process.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| P1 | `generate_day_notes` session type detection is a string match list | New iRacing session types (e.g., "Warmup", "Lone Qualify") may not be caught | Add to list as discovered, or switch to "skip header if `## ` + timestamp pattern found" |
| P2 | ~~CLI argument parsing for paths with spaces fails~~ | ~~Specific file processing silently fails~~ | **FIXED** — joined non-flag args as single path |
| P3 | **Race results only attach to telemetry — no standalone results processing** | If telemetry didn't record (forgot to start, crashed, wrong setting) but you have a race result, there's no way to ingest it into Tenths. Results are orphaned unless a matching .ibt exists. | **High priority** — fix at later time |

### P3 Details — Standalone Race Results Gap

**Problem:** The current model assumes results are always a supplement to .ibt telemetry. But there are real scenarios where you have results without telemetry:
- Forgot to enable telemetry recording
- Tenths wasn't running and files were lost/not archived
- iRacing crashed mid-session (partial .ibt, no valid laps)
- Want to track iRating/results history for sessions where you didn't analyze telemetry

**Desired behavior:** A command like `tenths results "path/to/eventresult.json"` that:
1. Parses the result file (positions, iRating, incidents, lap times)
2. Creates a minimal session entry (car/track/date from result metadata)
3. Generates a session_summary.json with race_result populated (no telemetry fields)
4. Appears in the master index with the race result but no "View Report" link
5. Contributes to iRating tracking and session count progression

**Why high priority:** Every race matters for tracking improvement. Missing a race from the index because telemetry didn't record defeats the purpose of Tenths as a progression tool.

### Future Enhancements (Process)

- **Reprocess workflow** — Add a `tenths reprocess [date]` or `tenths reprocess --today` command that scans the archive for files matching a date and re-runs the full pipeline. Useful when: forgot to start Tenths, track map was updated, or want to regenerate reports after a code change.
- **Better "no files" diagnostics** — When `tenths process` finds nothing, report WHY: "0 .ibt files in telemetry root (5 files under 1MB minimum, 3 files in archive from today)". Helps the user understand if files were already processed vs. genuinely missing.


## Track Map System (`tenths/track_map.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| TM1 | **Filename matching is fragile** — `load_track_map()` fuzzy matcher strips underscores from filenames but NOT from the search slug | iRacing slug `roadamerica_full` doesn't match file `road_america_full.md`. Silently falls through to no map or loads an auto-generated skeleton instead of the hand-tuned file. Affects any track where iRacing naming differs from our file naming. | **High priority** — fix before next release |
| TM2 | **`get_turn_name()` uses closest-center with 4% tolerance** — when two turns are close together, the braking zone maps to the wrong one | At Road America, 76.9% (Canada Corner braking zone) matched to T11 Kink (center 72%) instead of T12 Canada Corner (center 81.5%) because it was closer to Kink's center. Any track with densely packed turns (>2 within 10%) is vulnerable. | **High priority** — fix before next release |
| TM3 | **Auto-generated skeletons can shadow hand-tuned maps** — if both `roadamerica_full.md` (skeleton) and `road_america_full.md` (tuned) exist, exact match wins | User must manually delete the skeleton after building a proper map. No warning or conflict detection. | Medium — add dedup check in `load_track_map()` |
| TM4 | **No canonical slug registry** — the mapping from iRacing .ibt filename slugs to track map files is implicit via fuzzy matching | No way to guarantee a specific file will be loaded for a given slug. Renaming a file can silently break lookups for all sessions at that track. | Medium — implement alias table |

### Proposed Fixes

**TM1-TM4 — RESOLVED: CrewChief trackLandmarksData integration (2026-07-22)**

The manual percentage-based track mapping system is being replaced with a data-driven approach using CrewChief's community-contributed `trackLandmarksData.json` (457 iRacing tracks with corner positions in meters).

**Data file:** `tenths/data/trackLandmarksData.json` (bundled, 985KB)
**Source:** CrewChief V4 (GPL-3.0, community-contributed corner data)

**Lookup order:**
1. Tenths bundled data (`tenths/data/trackLandmarksData.json`) — self-contained, always available
2. CrewChief install (`C:\Program Files (x86)\Britton IT Ltd\CrewChiefV4\trackLandmarksData.json`) — fallback for newer data

**Implementation plan:**
1. New function `load_track_from_landmarks(ir_track_slug)` in `track_map.py`:
   - Reads `trackLandmarksData.json`
   - Finds entry where `irTrackName` matches the slug from .ibt filename
   - Converts `distanceRoundLapStart/End` to track percentage using `approximateTrackLength`
   - Returns the same zone list format as `load_track_map()` currently returns
   - Corner names come from `landmarkNames` array (e.g., "turn1", "the_esses", "canada_corner")

2. Modified `load_track_map()` lookup order:
   - First: check bundled `trackLandmarksData.json` by slug (covers 457 tracks)
   - Second: check hand-tuned `tracks/*.md` files (for tracks with custom coaching notes)
   - Third: fallback to CrewChief install path (newer data)
   - Fourth: return empty (skeleton will be auto-generated from GPS)

3. `get_turn_name()` fix: use distance-based matching (meters from S/F) instead of percentage ranges. The landmarks data provides exact start/end distances — a braking zone at 3360m matches the landmark whose range contains 3360m. No ambiguity, no tolerance hacks.

**Benefits:**
- Eliminates manual track mapping entirely for 457 tracks
- No more percentage-guessing or screenshot interpretation
- Slug matching is exact (the JSON uses the same slugs as .ibt filenames)
- Corner names are standardized across the community
- Self-contained — works without CrewChief installed

**What remains manual:**
- Custom coaching notes in `tracks/*.md` (performance history, coaching sentences)
- Tracks not in CrewChief's database (rare/new tracks)

### Workarounds (current state)
- Track map filenames must exactly match the iRacing slug (e.g., `roadamerica_full.md` not `road_america_full.md`)
- Percentage ranges in track maps must be set so braking zones land clearly inside the correct turn's range, accounting for the 4% tolerance and closest-center algorithm
- If both a skeleton and tuned map exist, delete the skeleton manually
