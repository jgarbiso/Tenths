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
| A1 | Braking zone detection only catches >50% brake pressure | Misses light-braking corners (e.g., 11 of 16 turns at Barber) | ~~When iRacing API provides official turn positions (Phase 5)~~ **Premise corrected 2026-09-03:** the iRacing API publishes **no** per-corner turn positions (only a count + an SVG image) — see `docs/IRACING_TRACK_API_INVESTIGATION.md`. The path to full-lap coverage is telemetry-derived sections (POST_MVP "Track Sections"), not an API. |
| A2 | Schema downgrade not prevented in migration system | If a newer Tenths version's JSON is opened by older version, it stamps the older schema | Before multi-user distribution |
| A3 | ~~Duplicate/near-identical braking zones~~ | **LARGELY RESOLVED 2026-07-29** by the distance-based zone split (`ZONE_GAP_METERS`). No duplicate turn labels remain on the Qualcomm, Mid-Ohio or Winton sessions. The unclamped-window fallback in `_apex_window` is retained as a guard. | Re-check if duplicates reappear |
| A4 | Corner sectors cover ~88% of the lap, not 100% | "Total recoverable" is the sum of corner sectors, not a true lap total. Honest but easy to misread as a full-lap figure. | Either label it explicitly in the UI or move to full Voronoi coverage |
| A5 | ~~Lap numbering differs from official iRacing results by one~~ | ~~Misdiagnosed as a label offset.~~ It was data misattribution: every lap carried the previous lap's time, so `best_lap` analysed the lap AFTER the real best. | **RESOLVED 2026-09-25** — lap times now come from `analyzer.lap_times`; see the resolution record below |
| A6 | ~~Spread/std thresholds are absolute mph~~ | ~~Misfires on fast corners~~ | **RESOLVED 2026-07-30 (RR-021)** — now speed-relative with a floor |
| A7 | ~~"High yaw — oversteer risk" fires on normal high-speed cornering~~ | ~~False-positive flags controlled trail braking at fast corners as oversteer.~~ | **RESOLVED 2026-09-02** — diagnosis reframed around lateral G in `analyzer.diagnose_trail_zone`; see the resolution record below |

### A5 Details — Lap Times Attributed to the Wrong Lap — RESOLVED 2026-09-25

**Original diagnosis (wrong):** "Tenths called the fastest lap #3; the result CSV called it #2. Times match exactly, only the label differs." That observation was correct, but it treated the mismatch as a numbering convention when the analysis itself was wrong.

**Real cause:** every lap time was read as `LapLastLapTime` at the lap's last sample. iRacing writes the completed lap's time into `LapLastLapTime` 13-117 samples (up to ~2 s at 60 Hz) *after* the `Lap` counter increments, so that sample still holds the previous lap's time. Each lap was labelled with its predecessor's time. The fastest *time* was still reported correctly, but it was attached to the following lap, and everything keyed on `best_lap` analysed that lap's telemetry: braking zones, trail braking, tyre temps, exit metrics, the corner-variance reference and the apex over-braking figure.

Evidence, Road Atlanta 2026-09-25 (Ford Mustang GT3): `Lap` goes from 1 to 2 at sample 11689, and `LapLastLapTime` becomes 88.288 at sample 11794. The true times were 88.29 / 83.78 / 82.13 / 92.13 / 82.47 / 82.23. The analyzer reported lap 3 = 83.78 and lap 4 = 82.12, so it chose lap 4 as best, and lap 4 was really the 92.1 s slow lap.

Side effects:
- The first timed lap after an out-lap ended with `LapLastLapTime` still 0, so `get_valid_laps` dropped it (`LapTime > 0`). It is now kept when it is a genuine complete lap. Road Atlanta: valid laps went from `[2..6]` to `[1..6]`.
- The last valid lap's own time was never read, because the lap after it was not analysed.

**Fix:** `analyzer.lap_times(df)` is the single source of lap times. Lap N's time is the first new `LapLastLapTime` value to appear after lap N's final sample, searched only within the following lap. If no new value appears, it uses `LapCurrentLapTime` at lap N's final sample, which matches the published time to within ~0.01 s. That fallback also covers two consecutive laps with identical times. `get_valid_laps`, `lap_summary`, `analyze`, both corner-variance paths and `_clean_lap_numbers` all call it.

**Why the tests missed it:** `tests/synthetic_ibt.py` wrote each lap's own time on that lap's samples, which is the behaviour the analyzer wrongly assumed. The generator now publishes each lap's time `LAST_LAP_TIME_DELAY_S` (1.7 s) into the next lap. With it, the old analyzer fails six ground-truth tests in `test_pipeline_synthetic.py`. Unit tests: `tests/test_lap_times.py`.

**Still unverified:** whether telemetry `Lap` numbers line up with the official results CSV numbering. No results CSV for an affected session was available to check. If they disagree by a constant, that really is only a label offset now.

### A7 Details — Trail Braking "High Yaw" False Positive — RESOLVED 2026-09-02

**Resolution:** The diagnosis now lives in one place, `analyzer.diagnose_trail_zone(brake_pct, lateral_g, yaw_rate)`, called by both `trail_braking_analysis` (console) and `_extract_trail_braking` (report). The authoritative explanation — thresholds, their measured provenance, and why each branch reads the way it does — is the block comment above that function. Do not restate it here; read it there.

**What changed, in brief:**
- High yaw at high lateral G is reported as controlled rotation ("High-speed rotation — normal for this corner speed" / "Good — combined load"), not oversteer. This is the ARA neutral-steer / three-tools-of-rotation case (see `SimCoach/CONTEXT.md`).
- The oversteer warning is kept only for the genuine signature: abnormal rotation, or high yaw with the brake on but *without* cornering load.
- Thresholds were calibrated against 469 trail zones from 40+ archived sessions across four car models. The old rule fired on 19% of them; every one was a false positive. The new classifier fires on zero.
- Guard tests: `tests/test_trail_zone_diagnosis.py`.

**Note on the earlier proposal:** the fix in `SimCoach/speed_delta_feature.md` Feature 4 proposed a yaw-to-steering-*rate* ratio. That signal was measured and rejected — raw steering rate at 60 Hz is dominated by single-sample spikes (20-67 rad/s) that make the ratio meaningless. The shipped fix uses lateral G instead, which is robust. `diagnose_trail_zone` deliberately takes no steering argument.

<details><summary>Original investigation (historical — the bug this resolved)</summary>

The old logic in `analyzer.py` was:
```python
if lat > 1.2 and brk > 30:
    diag = "Good"
elif brk > 60 and lat < 0.5:
    diag = "Braking straight"
elif yaw > 0.5 and brk > 20:
    diag = "High yaw — oversteer risk"
else:
    diag = "Light trail"
```
The "Good" check required brake > 30%. Once the driver had progressively released below 30% (the *correct* technique), the zone fell through to the yaw check, and at high-speed corners (2.0-2.7 G) normal cornering forces produce yaw > 0.5 with no oversteer — so textbook trail braking was flagged as "oversteer risk." Verified on Watkins Glen T1 (2026-08-26 practice, lap 7): brake 23%, 2.72 G, yaw 0.63, actively steering — controlled rotation flagged as oversteer. The same corner in the race read "Light trail" only because yaw was 0.48, just under the threshold. This produced a false narrative of persistent "T1 oversteer" across Tsukuba, Sonoma and VIR sessions.

</details>

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
| TM2 | ~~`get_turn_name()` uses closest-center with a percentage tolerance~~ — a lap-% tolerance meant wildly different distances per track (946 m at the Nordschleife vs 21 m at a bullring), turning "no match" into a confidently wrong neighbour | ~~Any track with densely packed turns is vulnerable.~~ | **PARTIALLY RESOLVED 2026-09-02** — tolerance is now a distance in metres (`DEFAULT_TOLERANCE_M`), consistent across track lengths; the exact-range match already handles the Road America Kink/Canada case (`test_boundary_no_ambiguity`) |
| TM3 | **Auto-generated skeletons can shadow hand-tuned maps** — if both `roadamerica_full.md` (skeleton) and `road_america_full.md` (tuned) exist, exact match wins | User must manually delete the skeleton after building a proper map. No warning or conflict detection. **Changed 2026-08-01 (RR-023):** generated maps now live in `%LOCALAPPDATA%\Tenths\tracks`, searched *before* bundled maps — so a generated skeleton now deliberately wins over a shipped map. Shadowing within the user dir is still undetected. | Medium — add dedup check in `load_track_map()` |
| TM4 | **No canonical slug registry** — the mapping from iRacing .ibt filename slugs to track map files is implicit via fuzzy matching | No way to guarantee a specific file will be loaded for a given slug. Renaming a file can silently break lookups for all sessions at that track. | Medium — implement alias table |

### Current Implementation and Remaining Work

The bundled landmark integration is active in `tenths/track_map.py`:

1. `load_track_map()` first calls `_load_from_landmarks()`.
2. `_load_from_landmarks()` reads the bundled `tenths/data/trackLandmarksData.json`, converts the iRacing filename slug from underscores to spaces, and performs an exact `irTrackName` lookup.
3. **Corner-distance overrides are applied first (added 2026-09-03).** `_apply_corner_overrides()` patches the corrupt corner *distance* records in the community file from the bundled `tenths/data/track_corner_overrides.json` (generated by `tools/build_track_corner_overrides.py`), keyed on iRacing `TrackID` when the caller passes one, else the slug. This runs **before** validation, so a repaired corner still faces the same guards. It repairs distances only; turn numbers are unchanged. iRacing has no API for corner positions — see `docs/IRACING_TRACK_API_INVESTIGATION.md`.
4. Landmark start/end distances are converted to percentages using `approximateTrackLength`. Records are validated at this step: a corner whose end is at or before its start, or well beyond the track length, is dropped and logged; a corner ending only marginally past the (approximate) length is clamped to the line rather than lost. `get_turn_name()` matches percentage ranges, then falls back to the nearest center within a **distance** tolerance (`DEFAULT_TOLERANCE_M`, converted per track and capped at `DEFAULT_TOLERANCE_PCT` so short tracks never loosen). See the resolved Track Data Integrity section in `POST_MVP.md`.
5. If no bundled landmark entry is found, `_load_from_md_file()` uses a legacy `tracks/*.md` map.
6. Frozen resource lookup uses `sys._MEIPASS`.
7. CrewChief is not searched or required at runtime.

This resolves most legacy slug/coverage problems for tracks present in the bundled data, but it does not make every old TM1-TM4 concern universally impossible. Legacy Markdown fallback matching remains fuzzy, generated maps can still need maintenance, and percentage conversion remains part of matching.

**Remaining release work:**

- **RR-001:** ~~Verify the exact landmark source revision, ownership, dataset-specific license, attribution, and redistribution obligations. The former GPL-3.0 assumption is not evidence.~~ **RESOLVED 2026-08-01.** Source is CrewChiefV4 (MIT, Britton IT Ltd). See `THIRD_PARTY_NOTICES.md`.
- **RR-015:** ~~Make `TENTHS_TRACKS_DIR` a real Markdown-map override. It is currently listed after built-in directories, and the loader stops at the first directory that exists even if it lacks the requested map.~~ **RESOLVED 2026-07-30.** Override is placed first and each candidate directory is searched for the specific file.
- Keep Tenths standalone; do not add a CrewChief installation dependency as a workaround.

### Current Workarounds

- Bundled landmark data remains the primary source for covered tracks.
- For an uncovered track, ensure a legacy Markdown filename can be found by the existing fallback matcher.
- If a generated fallback map conflicts with a hand-tuned map, remove or rename the generated file until explicit conflict handling is implemented.
