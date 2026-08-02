# Technical Debt

> **Release source of truth:** Use [`RELEASE_REMEDIATION_PLAN.md`](RELEASE_REMEDIATION_PLAN.md) for current priorities, implementation instructions, required tests, and acceptance criteria. Some historical proposals below no longer describe the implemented architecture.

Items identified during development that are acceptable for current use but should be addressed before production distribution.

---

## Watcher (`tenths/service/watcher.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| W1 | `_set_low_priority()` lowers entire process priority, not per-thread | Main loop also runs at below-normal during processing | Before adding tray UI in same process (Tier 3) |
| W2 | `_can_open_exclusive()` uses shared read, not true exclusive lock | Could theoretically trigger if iRacing allows read while still writing | If false triggers observed in production |
| W3 | ~~No processing of pre-existing .ibt files on startup~~ | ~~Files present before watcher starts are missed~~ | **RESOLVED 2026-07-30 (RR-005)** — `_scan_existing()` runs after the observer is live |
| W4 | `_states` dict grows unbounded (was `_processed`) | One small record per .ibt seen since start. Negligible for typical use; replaced the old set in RR-004 and now also carries attempt counts and errors. | If the watcher runs for weeks; evict DONE records by age |

## Analyzer (`tenths/analyzer.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| A1 | Braking zone detection only catches >50% brake pressure | Misses light-braking corners (e.g., 11 of 16 turns at Barber) | When iRacing API provides official turn positions (Phase 5) |
| A2 | Schema downgrade not prevented in migration system | If a newer Tenths version's JSON is opened by older version, it stamps the older schema | Before multi-user distribution |
| A3 | ~~Duplicate/near-identical braking zones~~ | **LARGELY RESOLVED 2026-07-29** by the distance-based zone split (`ZONE_GAP_METERS`). No duplicate turn labels remain on the Qualcomm, Mid-Ohio or Winton sessions. The unclamped-window fallback in `_apex_window` is retained as a guard. | Re-check if duplicates reappear |
| A4 | Corner sectors cover ~88% of the lap, not 100% | "Total recoverable" is the sum of corner sectors, not a true lap total. Honest but easy to misread as a full-lap figure. | Either label it explicitly in the UI or move to full Voronoi coverage |
| A5 | Lap numbering differs from official iRacing results by one | Tenths called the fastest lap #3; the result CSV called it #2. Times match exactly, only the label differs. | Align numbering, or note the offset where laps are displayed |
| A6 | ~~Spread/std thresholds are absolute mph~~ | ~~Misfires on fast corners~~ | **RESOLVED 2026-07-30 (RR-021)** — now speed-relative with a floor |

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

### Current Implementation and Remaining Work

The bundled landmark integration is active in `tenths/track_map.py`:

1. `load_track_map()` first calls `_load_from_landmarks()`.
2. `_load_from_landmarks()` reads the bundled `tenths/data/trackLandmarksData.json`, converts the iRacing filename slug from underscores to spaces, and performs an exact `irTrackName` lookup.
3. Landmark start/end distances are converted to percentages using `approximateTrackLength`; `get_turn_name()` still matches percentage ranges/centers rather than raw telemetry distance.
4. If no bundled landmark entry is found, `_load_from_md_file()` uses a legacy `tracks/*.md` map.
5. Frozen resource lookup uses `sys._MEIPASS`.
6. CrewChief is not searched or required at runtime.

This resolves most legacy slug/coverage problems for tracks present in the bundled data, but it does not make every old TM1-TM4 concern universally impossible. Legacy Markdown fallback matching remains fuzzy, generated maps can still need maintenance, and percentage conversion remains part of matching.

**Remaining release work:**

- **RR-001:** ~~Verify the exact landmark source revision, ownership, dataset-specific license, attribution, and redistribution obligations. The former GPL-3.0 assumption is not evidence.~~ **RESOLVED 2026-08-01.** Source is CrewChiefV4 (MIT, Britton IT Ltd). See `THIRD_PARTY_NOTICES.md`.
- **RR-015:** ~~Make `TENTHS_TRACKS_DIR` a real Markdown-map override. It is currently listed after built-in directories, and the loader stops at the first directory that exists even if it lacks the requested map.~~ **RESOLVED 2026-07-30.** Override is placed first and each candidate directory is searched for the specific file.
- Keep Tenths standalone; do not add a CrewChief installation dependency as a workaround.

### Current Workarounds

- Bundled landmark data remains the primary source for covered tracks.
- For an uncovered track, ensure a legacy Markdown filename can be found by the existing fallback matcher.
- If a generated fallback map conflicts with a hand-tuned map, remove or rename the generated file until explicit conflict handling is implemented.
