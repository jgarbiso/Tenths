# Tenths Release Remediation Plan

**Status:** Active source of truth  
**Review date:** 2026-07-28  
**Last updated:** 2026-07-30 — 11 of 22 issues resolved, 1 deferred by owner, 1 new issue opened (RR-022). Suite at 467 passing, zero skips. Distribution remains **NO-GO**: RR-001 (licensing), RR-006 (per-session manual output), RR-009 (offline claims), RR-011 (signing), RR-017 (docs), RR-018, RR-019 and RR-022 are open.  
**Target:** Public distribution after all release gates are closed  
**Current version:** 0.9.0  
**Repository:** `c:\Users\justi\Documents\Sim\Tenths`

This document converts the independent release review into implementation-ready work for another developer or AI model. Treat it as the canonical source for release blockers and remediation status. Older plans and handoff notes may describe behavior that has since changed.

## 1. Mandatory execution contract

Before changing code:

1. Read `c:\Users\justi\Documents\Sim\.kiro\steering\tenths-development.md`.
2. Read this entire document and the files named by the issue being addressed.
3. Inspect the working tree before editing. Preserve and understand existing changes; never discard them merely to obtain a clean tree. If unrelated changes are present, keep remediation edits isolated.
4. Do not commit unless the user explicitly requests a commit.
5. Do not weaken, delete, or skip tests to make a change pass.
6. Tests must execute production behavior; placeholders such as `assert True` are forbidden.
7. After every code change, run from the Tenths root:
   ```cmd
   python -m pytest tests/ -v --tb=short
   ```
8. For JavaScript changes in `report.py`, regenerate a real report, open it in the default browser, and inspect the browser console.
9. Use `webbrowser.open()` only. Never hardcode Chrome or another browser.
10. Preserve notification-first tray behavior; do not automatically open reports by default.
11. Every telemetry session must receive its own output folder and report. A faster session must never replace or suppress another session.
12. Keep Tenths standalone. CrewChief must not be required at runtime.
13. Prefer resource-efficient, event-driven behavior suitable for a constrained sim-racing PC.
14. Do not modify the real Windows registry from automated tests.

## 2. Verified baseline

At review time:

- Branch `main`, `HEAD` and `origin/main` at `4a473d4`.
- Full suite: **224 passed, 0 failed, 0 skipped** in 7.92 seconds.
- `python -m compileall -q tenths` passed.
- `python -m pip check` reported no broken requirements.
- Clean PyInstaller 6.21.0 build produced `dist\Tenths\Tenths.exe`.
- EXE size was approximately 14.1 MB; full bundle approximately 90.4 MB.
- The frozen app remained alive during a three-second tray startup smoke test.
- Inno Setup, Ruff, mypy, and `pip-audit` were unavailable.
- The executable was unsigned and had no Windows product/version/company metadata.
- The suite executed a real registry-mutating tray test. `HKCU\...\Run\Tenths` was absent afterward, but its prior state is unknown. Do not restore or alter it without user direction.

Do not assume these results remain current. Re-run the applicable checks after implementation.

### Preserve these verified strengths

Remediation must not regress the following behavior:

- Summary remains the default report view; Detailed retains the original telemetry dashboard.
- Tray mode notifies instead of automatically opening reports.
- Reports open through `webbrowser.open()` and the user's default browser.
- Watcher remains event-driven rather than polling the directory continuously.
- Frozen `sys._MEIPASS` resource lookup continues to package icon, legacy maps, and landmark JSON.
- Tenths remains standalone; CrewChief is not a runtime dependency.
- Installer remains per-user unless the owner explicitly changes that policy.
- Index path/XSS hardening and dependency constraints remain intact.
- No customer ID or developer-local account value may be hardcoded.
- Coaching must explain both where time was lost and why.

## 3. Severity and implementation order

| ID | Severity | Summary | Depends on |
|---|---|---|---|
| RR-001 | Release gate | Landmark and dependency licensing/notices | Human verification of source terms |
| RR-002 | Release blocker | ~~NumPy values serialize as strings and cause false PB badges~~ **RESOLVED 2026-07-30** | None |
| RR-003 | Release blocker | ~~Progression cannot traverse canonical date/time session layout~~ **RESOLVED 2026-07-30** | RR-006 stage A path helper |
| RR-004 | Release blocker | ~~Watcher failures are silent, permanent, and not retried~~ **RESOLVED 2026-07-29** | None |
| RR-005 | Release blocker | ~~Watcher misses files present at startup~~ **RESOLVED 2026-07-30** | RR-004 state model |
| RR-006 | Release blocker | Manual processing emits one representative report per day | None |
| RR-007 | High | ~~Manual processing is not failure-isolated or transactional~~ **DEFERRED 2026-07-30** by owner decision — beta testers use the watcher, not manual processing | RR-006 |
| RR-008 | High | ~~GT3 and most cars are mislabeled as Touring~~ **RESOLVED 2026-07-30** | None |
| RR-009 | High | Detailed report is not offline despite product claims | RR-001 if assets are bundled |
| RR-010 | High | ~~Race-result parsing aborts on malformed row values~~ **RESOLVED 2026-07-30** | None |
| RR-011 | High | Executable is unsigned and lacks metadata — **metadata done 2026-07-30, signing still open** | Release credentials for signing |
| RR-012 | Medium | ~~First-run telemetry guidance is ineffective~~ **RESOLVED 2026-07-29** — path resolution fixed, settings file, `tenths config`, one-time hint | None |
| RR-013 | Medium | ~~Tray tracks the latest report before processing completes~~ **RESOLVED 2026-07-29** with RR-004's `on_complete` callback | None |
| RR-014 | Execution prerequisite | ~~Tests mutate HKCU and depend on developer-local data~~ **RESOLVED 2026-07-29** | None |
| RR-015 | Medium | ~~`TENTHS_TRACKS_DIR` is shadowed by built-in directories~~ **RESOLVED 2026-07-30** | None |
| RR-016 | Medium | ~~Summary threshold differs between specs and implementation~~ **RESOLVED 2026-07-30** | Product decisions |
| RR-017 | Medium | User documentation contains incorrect feature/behavior claims | Functional fixes above |
| RR-018 | Medium | Uninstall retention and process-kill policy is undocumented | Product decision |
| RR-019 | Low | Bundle size and hidden imports need profiling | Functional blockers first |
| RR-020 | Low | ~~Frozen startup command has unnecessary CLI arguments~~ **RESOLVED 2026-07-30** | None; not a startup blocker |
| RR-021 | High | ~~Min-speed spread threshold is absolute mph and misfires on fast corners~~ **RESOLVED 2026-07-30** | Product decision; RR-016 |
| RR-022 | Medium | Over-braking rule never fires; limit is ~3× too high to trigger | Opened by RR-021 validation |

Recommended batches:

0. **Safe test prerequisite:** RR-014. Fix the registry test first; after that change, the mandatory full suite will exercise the isolated replacement rather than the destructive test.
1. **Legal gate:** RR-001 can proceed independently and may require human verification.
2. **Canonical paths:** RR-006 stage A introduces the shared output-path helper and command-specific artifact contract.
3. **Data correctness:** RR-002 and RR-003.
4. **Pipeline durability:** finish RR-006, then RR-004, RR-005, RR-007, RR-012, and RR-013.
5. **Analysis/report correctness:** RR-008 through RR-010, RR-016, and RR-021.
6. **Documentation and overrides:** RR-015 and RR-017.
7. **Distribution polish:** RR-011 and RR-018 through RR-020.

Run the complete mandatory suite after each logical code change, not only after the whole batch. RR-014 is first specifically so subsequent full-suite runs do not mutate the real registry.

## 4. Canonical output contract

All processing entry points must converge on this structure:

```text
<telemetry-root>\<car>\<track>\<YYYY-MM-DD>\<HH-MM-SS>\
    session_report.html
    session_notes.md
    session_summary.json
```

Rules:

- Watcher, manual `process`, standalone `report`, and standalone `summary` must use the same path builder.
- Watcher and manual `process` must produce report, notes, and summary for every successfully processed telemetry session.
- Standalone `report` and `summary` retain their current single-artifact command semantics, but write that artifact into the same canonical per-session directory. Changing those commands to generate all artifacts requires an explicit product decision.
- Never choose one representative session for a day.
- Never overwrite a session because another session is faster.
- If a target folder already exists for a different source file, create a deterministic collision-safe suffix rather than overwrite it.
- Processing commands archive an `.ibt` only after their required artifacts are successfully written; standalone generation commands do not implicitly archive input.
- Index generation is recoverable and may be retried, but watcher/`process` report, notes, and summary generation is required for processing success.
- Historical traversal must support multiple sessions on the same date and earlier dates.

## 5. Issue specifications

### RR-001 — Establish third-party provenance and notices

**Classification:** Release gate; unresolved facts, not a proven violation.

**Evidence:**

- Bundled file: `tenths/data/trackLandmarksData.json`.
- `LICENSE` covers Tenths only.
- The frozen bundle has no comprehensive third-party notices file.
- `docs/TECH_DEBT.md` and the old `docs/HANDOFF.md` called the data GPL-3.0 without verified dataset-specific evidence.
- The archived CrewChief GitHub repository identifies that repository as MIT and redirects development to GitLab; current dataset-specific terms were not verified.

**Required work:**

1. Identify and record the exact source URL, repository revision/commit, retrieval date, dataset owner, and whether Tenths modified the file.
2. Verify the terms that apply to this exact dataset. Do not infer them from an unrelated repository-level badge or stale local note.
3. Obtain human/legal confirmation if terms remain ambiguous; an AI model must not invent a license conclusion.
4. Add a root-level `THIRD_PARTY_NOTICES.md` covering the dataset and every dependency shipped in the frozen application.
5. Include required license/notice files in `installer/tenths.spec` and verify them in `dist\Tenths`.
6. Correct all provenance statements in README, handoff, and technical-debt documents.

**Acceptance criteria:**

- Exact dataset source and revision are reproducible.
- Redistribution and attribution obligations are documented and satisfied.
- Notices are present in both source and frozen distributions.
- No document makes an unsupported GPL/MIT assertion.
- If rights cannot be established, remove the dataset from distributed artifacts and retain the legacy Markdown fallback.

### RR-002 — Normalize JSON values and eliminate false PB badges

**Files:** `tenths/summary.py`, `tenths/report.py`, summary/report tests.

**Root cause:** `json.dump/json.dumps(..., default=str)` converts unsupported NumPy scalars such as `numpy.bool_(False)` to the string `"False"`. JavaScript treats that nonempty string as true.

**Reconfirmed live 2026-07-29:** both Qualcomm race summaries were written with `"is_new_pb": "True"` as a JSON string. Both were genuine PBs so the badge was coincidentally correct — this defect stays invisible until a non-PB session, which is exactly when it misleads.

**Required implementation:**

1. Add one shared JSON-normalization function used by summaries and reports.
2. Convert `numpy.generic` with `.item()`, arrays with `.tolist()`, and recursively normalize dict/list/tuple values.
3. Return native `bool`, `int`, `float`, `str`, and `None` values.
4. Reject or clearly fail on unsupported types instead of silently stringifying them.
5. Remove `default=str` from production JSON serialization after normalization.
6. Decide and document whether tying an existing PB counts as a new PB; preserve existing behavior unless the user chooses otherwise.

**Required tests:**

- Production serializer with `numpy.bool_(False)` emits JSON `false`, not `"False"`.
- NumPy true, integer, float, and array values retain correct JSON types.
- Generated report embeds `"is_new_pb": false` for a non-PB NumPy input.
- Generated summary can be loaded and all PB flags are actual Python booleans.
- Unsupported objects fail predictably.

**Acceptance criteria:** No persisted summary contains string values `"True"` or `"False"` for boolean fields, and a real non-PB report does not show the New PB badge.

**Resolution (2026-07-30).**

New module `tenths/jsonio.py` holds one normalizer used by both writers. `normalize()` converts `numpy.generic` via `.item()`, `numpy.ndarray` via `.tolist()`, recurses through dict/list/tuple, passes native scalars and `None` through, and converts `datetime`/`date` to ISO strings. Anything else raises `TypeError` naming the offending type and path, so an unsupported object fails loudly instead of becoming a plausible-looking string. `dump()`/`dumps()` wrap `json` with normalization applied first and **`default=str` removed** from production paths — that argument was the actual defect, not NumPy.

`summary.py` and `report.py` both call it, so the summary file and the report's embedded JSON blob can no longer disagree. `is_new_pb` is now computed as a real `bool`. Tying an existing PB is **not** a new PB, which is the pre-existing behavior and was left unchanged.

Tests in `tests/test_batch_a.py` assert the production serializer, not a copy of its logic: `numpy.bool_(False)` emits JSON `false`; NumPy true/int/float/array keep correct JSON types; a generated report embeds `"is_new_pb": false` for a non-PB NumPy input; every PB flag in a real generated summary is a Python `bool`; an arbitrary object raises. Verified against both Qualcomm races, which now write `"is_new_pb": true` as a JSON literal.

### RR-003 — Make progression understand nested per-session history

**Files:** `tenths/summary.py`, `tenths/process.py` baseline lookup, `tests/test_progression.py`.

**Root cause:** `compute_progression()` assumes `session_dir` is the date folder and scans only direct sibling directories. Watcher output passes a time folder, causing the function to scan only sibling times under the current date and miss prior dates.

**Confirmed symptoms observed 2026-07-29** (Ferrari at Qualcomm, two races plus the previous night):

- **Self-comparison on reprocess.** The current session is skipped only when the directory name equals the session date. A time-level folder never matches, so reprocessing a session reads its own previous `session_summary.json` as the "previous session": the 2026-07-28 20-57-02 summary reports `previous_session.date = 2026-07-28`, `delta_vs_previous = +0.000s` and `session_count = 2` while comparing against itself. Exclusion must be by normalized absolute path.
- **Missing cross-date history.** The first race of 2026-07-29 reported `progression: None` despite three prior sessions at the same car/track, so it showed "First Session" and no PB check.
- **Correct only by accident.** The second race of 2026-07-29 did find the first race, because both are siblings under the same date and progression is computed before the current summary is written. Ordering, not correctness.

**Required implementation:**

1. Reuse the canonical path helper introduced in RR-006 stage A to locate the car/track root, or pass that root explicitly; do not create a second path interpretation inside `summary.py`.
2. Discover `session_summary.json` files under `date/time` folders across the entire car/track root.
3. Exclude the current summary by normalized absolute path, not by date alone.
4. Sort by a complete session timestamp using summary date and time, with path values as a guarded fallback.
5. Support multiple sessions on one date.
6. Skip malformed, unreadable, or schema-incompatible summaries without aborting all progression; log diagnostics.
7. Update `load_baseline()` and any history code that still assumes date-level artifacts.
8. Avoid unbounded expensive scans: scan only the current car/track tree and consider a single reusable discovery helper.

**Required tests:**

- Prior-day nested session is found from `date/time/current`.
- Earlier same-day session is found and ordered before the current session.
- Current summary is excluded without excluding another session on the same date.
- Malformed history is skipped while valid history remains usable.
- Previous-session, all-time-best, count, and trend arrays use chronological order.
- Tests use the same canonical layout as the watcher.

**Acceptance criteria:** A first session on a new day uses previous-day history, and two sessions on one day each retain distinct progression entries.

**Resolution (2026-07-30).**

`compute_progression()` was rewritten rather than patched, because every one of its assumptions about the directory layout was wrong.

- `_find_track_dir()` walks up from the given directory to the car/track root, accepting either a date folder or a `date/time` folder, so watcher and manual paths converge without a second path interpretation.
- `_find_session_summaries()` discovers every `session_summary.json` beneath that root, at both `date/time` and legacy date level.
- The current session is excluded by `os.path.normcase(os.path.abspath(...))`, not by date. This is what fixed the self-comparison: a reprocessed session was reading its own prior summary and reporting `+0.000s` against itself.
- Ordering uses summary `date` plus `time`, with path components as a guarded fallback, and history is filtered to sessions **strictly earlier** than the current one.
- Malformed, unreadable or schema-incompatible summaries are skipped with a logged diagnostic; one bad file no longer voids all progression.
- Scanning is confined to the current car/track tree.

Two further defects surfaced during implementation and are fixed here: a **later** session was being selected as "previous" when files were discovered out of order (the strictly-earlier filter closes this), and a legacy date-level copy of the same session compared against itself in a second track layout (identity dedupe on date+time+lap time closes this).

`tests/test_progression.py` covers prior-day discovery from `date/time/current`, same-day ordering, exclusion of the current summary without excluding a sibling, malformed history skipping, chronological trend arrays, the future-session guard, and the duplicate-layout case — all built on the canonical watcher layout. Verified on the real Ferrari/Qualcomm tree: the first race of 2026-07-29 now finds the 2026-07-28 session instead of reporting "First Session".

### RR-004 — Introduce durable watcher processing states and visible failure handling

**Files:** `tenths/service/watcher.py`, `tenths/service/notifier.py`, configuration/logging code, watcher tests.

**Root cause:** `_processed` is populated before work starts. Exceptions only print to a hidden console; no retry or error notification occurs.

**Required implementation:**

1. Replace the single `_processed` set with explicit thread-safe states such as pending, in-progress, succeeded, and retryable-failed.
2. Deduplicate only active/successful work; a transient failure must be eligible for retry.
3. Add bounded retries with backoff. Do not use a busy loop.
4. After retries are exhausted, retain the source `.ibt`, show `notify_error()`, and write a durable UTF-8 log with timestamp, source path, stage, and exception.
5. Mark success only after report, notes, summary, notification attempt, and archive policy complete as defined.
6. Keep notification failure and index regeneration nonfatal, but log them.
7. Ensure shutdown/pause cannot start duplicate observer or processing threads.
8. Do not automatically open reports in tray mode.

**Required tests:**

- A transient first failure retries and then succeeds exactly once.
- A permanent failure is not archived, produces an error notification, and is logged.
- A successful file is not processed twice after duplicate events.
- State transitions are thread-safe and deterministic without real sleeps.
- Tests mock notifier and filesystem state rather than displaying real notifications.

**Acceptance criteria:** No processing exception can become invisible in the packaged `console=False` application, and a retryable file is not permanently stranded in memory state.

**Resolution (2026-07-29).**

- **Durable logging.** New `tenths/applog.py` writes a rotating UTF-8 log to `%LOCALAPPDATA%\Tenths\logs\tenths.log` (2 MB × 3, the path the installer already removes on uninstall). A console handler is added only when stdout exists, so `tenths watch` still prints while the frozen tray logs silently to file. Setup never raises: an unwritable log directory degrades to no file logging rather than killing the app. `cli.main` and `tray.main` both configure it, and the tray logs unhandled exceptions via `log.exception`.
- **Explicit state model.** `_processed` is replaced by `_states` under an `RLock`, with `FileState.PENDING / IN_PROGRESS / DONE / FAILED`. `_claim()` dedupes duplicate filesystem events and concurrent workers but still permits a retry, which the old set could not.
- **Bounded retries.** `MAX_ATTEMPTS = 3` with `RETRY_BACKOFF_SECONDS = (10, 45)`. Retries are dispatched from the existing 2-second stability tick, so there is no busy loop and no extra thread.
- **Failures surface.** Retryable failures log a warning; exhausting attempts logs an error with traceback, calls `notify_error()`, and leaves the `.ibt` in place. A broken notifier is itself logged rather than masking the original error. On shutdown the watcher lists every session that could not be processed.
- **Success is earned.** `REQUIRED_ARTIFACTS` (report, notes, summary) must all exist before the source is archived; a missing artifact raises and triggers the retry path. Notification, index regeneration, browser opening and archiving are individually nonfatal but logged — a failed archive no longer discards a session whose outputs succeeded.
- **Permanent conditions are not retried.** An unparseable filename or an `.ibt` with no valid laps is logged and closed out, since a retry cannot change either.
- **No duplicate observers.** `start()` refuses to run twice; the tray no longer monkey-patches `_on_file_ready` and instead receives an `on_complete(report_path)` callback, which also fixes RR-013.

Verified end to end: a stub failing twice then succeeding produced 3 attempts, state `done`, and no user-facing alarm; a permanently failing stub produced 3 attempts, state `failed`, an error notification reading `processing: disk full`, and the source retained. A real fixture processed cleanly, writing all three artifacts, archiving afterwards, and firing `on_complete` with the report path. `tests/test_watcher_reliability.py` adds 26 tests; suite 369 passed.

Also fixed here: RR-013 (tray now learns the report path on completion). Not addressed: the watcher's `telemetry_root` argument controls what it watches, but `_run_pipeline` writes to the global `config.TELEMETRY_ROOT`. Those differ only when the argument is used, which today is tests. Fold into RR-006's canonical path work.

### RR-005 — Process existing telemetry when the watcher starts

**Files:** `tenths/service/watcher.py`, watcher tests.

**Required implementation:**

1. After the observer/handler is ready, perform one nonrecursive scan of the telemetry root for `.ibt` files.
2. Feed candidates through the same stability, minimum-size, deduplication, and retry path as filesystem events.
3. Do not process files in `_archive`, generated car/track directories, or temporary/partial files.
4. Avoid a race between initial scanning and create/modify events by relying on the shared state model from RR-004.

**Required tests:**

- A qualifying pre-existing file is scheduled once.
- A too-small file is not processed.
- A file found by both startup scan and an event is processed once.
- A file that becomes stable after startup is eventually scheduled without CPU-heavy polling.

**Acceptance criteria:** A valid `.ibt` created while Tenths was stopped is processed after the next startup without manual modification.

**Resolution (2026-07-30).**

`TelemetryWatcher._scan_existing()` runs once after the observer is live, doing a nonrecursive listing of the telemetry root and routing every `.ibt` through `IBTHandler.track_existing()` — the same stability, minimum-size, dedupe and retry path as a filesystem event. It reuses RR-004's `_claim()`, so a file seen by both the scan and a create event is processed exactly once; there is no separate code path to keep in sync and no scan-versus-event race.

The scan is nonrecursive by design: `_archive` and the generated `car/track/date/time` output tree both live under the root, and recursing would reprocess archived sessions forever. Temporary and partial files are excluded by the existing minimum-size and stability checks rather than by name matching.

`tests/test_watcher_reliability.py` covers a qualifying pre-existing file being scheduled once, a too-small file being ignored, a file found by both scan and event being processed once, a file that only becomes stable after startup still being picked up on a later tick, and archived files being left alone.

### RR-006 — Make manual and standalone processing per-session

**Files:** `tenths/process.py`, `tenths/report.py`, `tenths/summary.py`, shared path helper, index tests as needed.

**Root cause:** Manual processing groups by `(car, track, date)`, emits date-level artifacts, and selects one representative session. Standalone report/summary commands also write date-level output.

**Required implementation:**

1. **Stage A:** introduce one canonical output-path helper implementing Section 4, including deterministic collision handling, and make watcher, manual process, report CLI, and summary CLI call it.
2. Preserve command semantics: watcher and `process` generate all three required artifacts; standalone `report` generates only the report; standalone `summary` generates only the summary.
3. **Stage B:** process and emit the full artifact set independently for every file handled by manual `process`.
4. Remove representative-session selection from artifact creation. Daily aggregation may exist only as an additional artifact and must not replace session outputs.
5. Preserve race-result matching per source session.
6. Regenerate the master index after the batch without hiding sessions.

**Required tests:**

- Two same-day files handled by watcher or `process` create two time folders and two complete artifact sets.
- A slower session handled by watcher or `process` still gets its report.
- Standalone `report` and `summary` each retain their single-artifact behavior while using the canonical time-level directory.
- Manual and watcher path generation are identical for the same filename metadata.
- Existing outputs are not silently overwritten on a collision.

**Acceptance criteria:** Every file successfully handled by watcher or `process` has its own report, notes, and summary. Standalone generation commands place their requested artifact in that same session-specific location without implicitly creating unrelated artifacts or archiving the input.

### RR-007 — Isolate manual failures and archive transactionally

**Files:** `tenths/process.py`, error-path tests.

**Required implementation:**

1. Catch analysis/output exceptions per file and continue with later files.
2. Report a batch summary of succeeded, skipped, and failed files with actionable reasons.
3. Archive only after all required artifacts for that file have been written successfully.
4. Leave failed source files discoverable for retry.
5. Handle a missing telemetry root gracefully: create it when appropriate or print clear setup guidance and exit without traceback.
6. Treat malformed optional race-result data as nonfatal to telemetry report generation.

**Required tests:**

- A corrupt first file does not block a valid second file.
- Output failure leaves the source unarchived.
- Successful output archives exactly once.
- Missing telemetry root exits cleanly and provides an actionable message.
- Batch outcome counts and file names are accurate.

**Acceptance criteria:** No individual corrupt input aborts the batch, and no source is archived before its required output is safely available.

**Deferred (2026-07-30) — owner decision, not a technical conclusion.**

The owner deferred this for the beta because beta testers install the tray app and never invoke `tenths process` by hand; the durability that matters for them is RR-004's watcher path, which is done. This is a scope decision on *when*, not a claim that the defect is absent. The specification above stays as written and RR-007 remains unchecked on the release gate.

Two consequences to keep in view: the batch failure-isolation gap is still present in `process.py` for anyone who does run it (the owner, and any tester given manual instructions), and RR-007 depends on RR-006, which is also still open. If manual processing is ever surfaced in user documentation, this must be reopened first.

### RR-008 — Use session metadata for car class and physics profile

**Files:** `tenths/analyzer.py`, report/summary consumers, production unit tests.

**Root cause:** `detect_car_class(vehicle)` recognizes five GT4 filename fragments and returns `Touring` for every other car, even though `parse_session_info()` already extracts `CarClassShortName`.

**Required implementation:**

1. Separate the displayed iRacing class from the internal diagnostic physics profile.
2. Prefer normalized `session_info['car_class_short']`; use filename heuristics only as a guarded fallback.
3. Do not label unknown, GT3, prototype, formula, or stock cars as Touring merely because no dedicated profile exists.
4. Define explicit profile selection. Until class-specific rules exist, use a clearly named generic profile rather than pretending it is Touring physics.
5. Pass metadata into production detection from `analyze()` and expose both class/profile fields where needed.
6. Preserve GT4-specific behavior for verified GT4 metadata and known fallback filenames.

**Required tests:**

- Invoke production detection for BMW M4 GT3 EVO and Ferrari 296 GT3 metadata; neither may return Touring.
- GT4 metadata selects the GT4 profile even when the filename is not in the old list.
- Known Touring metadata selects Touring.
- Missing metadata follows a documented generic/fallback path.
- Tests must call production functions rather than repeat their arithmetic or string logic.

**Acceptance criteria:** Generated GT3 reports show the correct iRacing class and do not claim Touring-specific physics.

**Resolution (2026-07-30).**

The displayed class and the physics profile are now two separate values, which was the root confusion — one function was being asked to answer both questions.

- `detect_physics_profile()` returns `PROFILE_GT4` or the new `PROFILE_GENERIC`. `"Touring"` no longer exists as a profile name, so no car is described as having Touring physics because nothing better was recognized. GT4 behavior is preserved for verified GT4 metadata *and* the original filename fragments.
- `detect_display_class()` prefers `session_info['car_class_short']` and falls back to the profile name.
- `analyze()` passes session metadata into both, so production reports use metadata rather than filename guessing.

One thing the original spec did not anticipate: `CarClassShortName` is not always human-readable. iRacing returns internal slugs such as `bmwm4evogt4` for some entries, and displaying that raw would be worse than the bug being fixed. `_is_human_readable_class()` gates it — a value is only shown if it looks like a label rather than a slug — and otherwise the profile name is used.

`tests/test_batch_a.py` calls the production functions (no re-implemented string logic) for BMW M4 GT3 EVO and Ferrari 296 GT3 metadata, neither of which may return Touring; GT4 metadata with an unrecognized filename; a genuine Touring class label; slug-shaped class values; and absent metadata. Verified on the real Ferrari races, which now report **"GT3 Class"**.

### RR-009 — Make the full report offline or narrow the product contract

**Files:** `tenths/report.py`, packaged assets/spec, README, Getting Started, report tests.

**Evidence:** Generated reports are a single local HTML file and require no server, but they reference Google Fonts, Leaflet from unpkg, and Chart.js from jsDelivr. Summary is locally implemented and satisfies the existing offline Summary requirement; Detailed charts/map depend on remote assets and report opening contacts third parties. “Single local file,” “no server/runtime API,” and “no outbound network requests” are separate properties.

**Product choice:**

- **Option A — fully offline report (preferred for the current README promise):** bundle pinned, license-compatible Leaflet and Chart.js assets; remove remote font requests; and make both views work without network access. Assets may be inlined to preserve a literally self-contained file, or packaged/referenced locally if product ownership accepts a multi-file report dependency.
- **Option B — retain current CDN-backed Detailed view:** keep the existing single-HTML/no-server contract, narrow all offline claims to Summary/analysis behavior, and disclose that opening Detailed contacts third-party CDNs.

For Option A:

1. Decide separately whether to preserve a literally single-file report or allow packaged local assets.
2. Use bundled fonts with verified terms or robust local/system fallbacks.
3. Include all required asset licenses in RR-001 notices.
4. Keep report viewing free of network calls.

**Required tests/manual checks:**

- For either option, Summary works with networking disabled and the documented behavior matches the artifact.
- For Option A, generated reports make no external asset requests; both views, map, charts, switching, and browser console work offline.
- For Option A, PyInstaller includes any assets needed during report generation or viewing.
- For Option B, tests preserve the formal single-HTML/no-server Summary contract and docs disclose Detailed-view CDN behavior.

**Acceptance criteria:** The implemented artifact and every user-facing claim agree. Option A provides a fully offline report; Option B remains one local HTML file with an offline Summary but a network-dependent Detailed view. Full offline behavior is preferred but is a product/release decision, not an existing formal requirement for Detailed.

### RR-010 — Harden race-result parsing

**Files:** `tenths/results.py`, race-result tests.

**Root cause:** CSV rows use direct `int(...)` conversion. One malformed value aborts the complete file. Customer IDs are compared without type normalization.

**Required implementation:**

1. Use a shared safe integer conversion for every numeric CSV field.
2. Normalize `my_cust_id` and row customer IDs to one canonical type.
3. Decide row policy explicitly: retain a row with safe defaults when possible; skip only structurally unusable rows and record a diagnostic.
4. Keep a malformed optional result from blocking telemetry analysis.
5. Apply comparable defensive normalization to JSON values.

**Required tests:**

- One malformed numeric CSV row does not discard valid rows.
- Blank iRating/license values become documented defaults.
- String and integer forms of the same customer ID match.
- Malformed JSON result values degrade safely.
- Fully unusable files return a controlled failure without traceback.

**Acceptance criteria:** A bad field or row cannot abort otherwise usable race results or the telemetry pipeline.

**Resolution (2026-07-30).**

Every numeric field in both `parse_csv_result()` and `parse_json_result()` now goes through `_safe_int`, including the metadata Strength of Field and the JSON lap-time fields. Previously a single blank iRating discarded the whole result file, taking the finishing position with it.

`_same_customer()` compares IDs type-insensitively: both sides are coerced with `_safe_int`, and if either resists coercion it falls back to a stripped string comparison. The `.ibt` header and the result file do not reliably agree on type, and the strict `==` silently failed to find the driver's own row — the report then lost its position and iRating with no error.

Row policy is explicit: rows are retained with safe defaults wherever possible, and only structurally unusable rows are dropped. In the JSON path, non-dict entries are filtered out *before* sorting. That ordering matters — the sort key calls `.get()`, so a non-object row raised while building the key and lost the entire file before any per-row handling could run. My own test caught this crash after the first version of the fix.

`tests/test_batch_a.py` covers a malformed numeric CSV row not discarding valid rows, blank iRating/license values becoming documented defaults, string-versus-int customer ID matching in both directions, malformed JSON values degrading safely, non-dict JSON rows being skipped without a traceback, and a fully unusable file returning a controlled `None`. Verified that the real event-result CSV still parses to the same values as before.

### RR-011 — Add Windows metadata, signing, and artifact-level verification

**Files:** `installer/tenths.spec`, version-resource file if introduced, `installer/build.py`, packaging tests/documentation.

**Required implementation:**

1. Embed product name, file description, company/publisher, file version, product version, and copyright metadata.
2. Keep version values synchronized with `pyproject.toml` and installer version through one source or a validation check.
3. Define a signing step for EXE and installer artifacts. Never fabricate or commit private signing credentials.
4. Obtain the actual signing certificate and secret handling from the project owner.
5. Add artifact checks that inspect the real built EXE, not only source configuration.
6. Build and test the Inno installer when Inno Setup is available.

**Acceptance criteria:**

- Windows properties show expected metadata and version.
- Release artifacts have a valid trusted signature, or the release remains explicitly blocked pending credentials.
- Clean install, launch, startup option, upgrade, and uninstall are smoke-tested on a clean Windows account/VM.
- Packaging tests verify required data, notices, metadata, and startup behavior.

**Partially resolved (2026-07-30) — metadata done, signing still blocked.**

Done: `installer/version_info.txt` supplies a Windows `VSVersionInfo` resource (company, file description, file/product version `0.9.0.0`, internal and original filename, copyright), and `installer/tenths.spec` references it from `EXE(version=...)`. The built executable now shows a product name and version in its Windows properties instead of appearing anonymous.

Two build-script defects were found and fixed while producing the first artifact with metadata, and both had been hiding each other:

- `tenths.spec` passed `SPECPATH` through `os.path.dirname()`. PyInstaller already sets `SPECPATH` to the spec file's *directory*, so `SPEC_DIR` pointed at the project root and `version_info.txt` resolved to `Tenths\version_info.txt`, which does not exist. The build aborted with `FileNotFoundError`. The spec now uses `SPECPATH` directly and fails with an explicit message naming the expected path, so the fix is never to silently drop the `version=` argument.
- `installer/build.py` printed a ✗ emoji on its failure path, which raised `UnicodeEncodeError` on a stock cp1252 console. The encoding error replaced the actual PyInstaller error in the output, so the first symptom of the spec bug was a traceback about a character map. `build.py` now reconfigures its streams to UTF-8 before printing anything.

**Verified on the real artifacts, 2026-07-30:**

- `dist\Tenths\Tenths.exe`, 14.2 MB, bundle 90.5 MB. `Get-Item ... .VersionInfo` reports ProductName `Tenths`, ProductVersion and FileVersion `0.9.0.0`, CompanyName `Justin Garbiso`, FileDescription `Tenths - iRacing telemetry coaching`, and the expected copyright and original filename. This is read from the built binary, not from the spec.
- Bundled resources present under `_internal`: `data\trackLandmarksData.json`, `tracks\`, `assets\tenths.ico`.
- `Get-AuthenticodeSignature` reports `NotSigned`, as expected.
- Inno Setup 6 turned out to be installed after all, so `installer\Output\TenthsSetup.exe` was built: 32.0 MB, ProductName `Tenths`, ProductVersion `0.9.0`, CompanyName `Justin Garbiso`.
- The frozen `Tenths.exe config` was run and printed the resolved Documents, iRacing, telemetry, archive, log and settings paths plus an unprocessed-file count, confirming the argv dispatch works in the packaged windowed build and not just from source.

Still open, and these are why RR-011 stays unchecked:

- **No signature.** Signing needs a real code-signing certificate, which is the owner's to obtain. No credential may be fabricated or committed, so this remains a release blocker rather than something to implement.
- **No version single-source.** `pyproject.toml`, `version_info.txt`, and `tenths_setup.iss` each carry the version independently. They agree today at 0.9.0 by hand; a validation check or single source is still required. Note the formats differ deliberately (`0.9.0` versus the four-part `0.9.0.0`), so a naive string comparison will not work.
- **No automated artifact assertion.** The verification above was manual. Packaging tests still read the spec rather than the built EXE, so a future regression would not be caught by the suite.
- **Installer not install-tested.** `TenthsSetup.exe` compiles, but the clean install, launch, startup toggle, upgrade and uninstall matrix has not been run on a clean Windows account or VM.
- **Inno Setup warning unaddressed.** The compile emits a warning that the `[UninstallRun]` entry has no `RunOnceId`. Folded into RR-018.

### RR-012 — Provide effective first-run telemetry guidance

**Files:** `tenths/config.py`, `tenths/service/watcher.py`, notifier/onboarding tests and docs.

Creating a missing telemetry folder currently looks like success, even when iRacing telemetry is disabled. Add a one-time, actionable first-run state that explains Alt+L/`irsdkLogAll=1`, the watched path, and how Tenths detects a first file. Do not repeatedly nag established users. Test the newly created empty-root path separately from filesystem creation failure.

**Acceptance criteria:** A new user cannot sit indefinitely with a healthy-looking tray app and no explanation of how to produce telemetry.

**Partially resolved (2026-07-29) — the misresolved-path cause is fixed.**

Root cause found while reviewing how the telemetry location is chosen: `config` resolved Documents with `os.path.expanduser("~/Documents")`, which is `%USERPROFILE%\Documents` and does **not** follow redirection. iRacing resolves it with the Windows Known Folder API, which does. They diverge whenever Documents has been moved — most commonly by OneDrive folder backup, which iRacing documents as a known problem. The naive path then points at a folder iRacing never writes to.

The damage was not the wrong path but what happened next: `_ensure_watch_root()` created that folder and returned success, so Tenths reported "monitoring", the tray looked healthy, and no report ever appeared — with no error, notification or log entry.

Fixed:

- `config._documents_dir()` resolves via `SHGetKnownFolderPath(FOLDERID_Documents)`, falling back to the `Shell Folders\Personal` registry value and only then to the naive join. Also removes a mixed-separator path (`C:\Users\x/Documents\...`) that would have appeared in bug reports.
- `config._find_iracing_telemetry()` is now side-effect free; it never creates a directory.
- `_ensure_watch_root()` uses `<Documents>/iRacing` as the signal. If that exists, only the `telemetry` subfolder is missing, which is safe to create. If it does not, Tenths refuses to watch and logs what to check, including the `TENTHS_TELEMETRY_ROOT` override, rather than inventing a decoy folder.
- The resolved path is logged on every start, so the first question about any "no report appeared" report is already answered.
- `TestD2_WatcherFolderGuard` updated: creating the folder is still correct when the location is verified, and now asserted to be refused when it is not.

**Completed (2026-07-29) — settings file and first-run guidance.**

- **Settings file.** `%LOCALAPPDATA%\Tenths\settings.json`, with precedence `TENTHS_TELEMETRY_ROOT` env → `telemetry_root` setting → auto-detection. An installed user will never set an environment variable, so this is the only realistic way to support an unusual iRacing layout. A malformed file is reported through `CONFIG_WARNINGS` and drained by the entry point once logging exists (`config` cannot import `applog`, which imports `config`), and never prevents startup. A configured-but-missing folder is reported rather than silently accepted.
- **`tenths config` command.** Prints the resolved Documents, iRacing, telemetry, archive, log and settings paths, flags any that are missing, and counts unprocessed `.ibt` files. `--telemetry-root <path>` sets the folder (validating it exists first), `--reset-telemetry-root` returns to auto-detection. This answers the first two support questions — which folder is being watched, and where is the log — without a developer in the loop.
- **One-time setup hint.** `_check_first_run()` runs at watcher start. If the root shows no sign of telemetry (no `.ibt` in the root, none in `_archive`, no processed session tree) it logs the Alt+L / `irsdkLogAll=1` instructions and shows a single `notify_info` toast, then records `setup_hint_shown` so established users are never nagged. A broken notifier cannot block startup.

**Follow-up fix (2026-07-30) — the frozen exe now honours arguments.** Writing `docs/BETA_TESTING.md` exposed that its own instruction could not work: the packaged build ships a single `console=False` executable whose entry point is `tray.main()`, which ignored `sys.argv` entirely. `Tenths.exe config` therefore started the tray and printed nothing, so the command that exists specifically to answer "which folder is being watched" was unreachable for every installed user — the only people who need it. `tray.main()` now forwards any arguments to `cli.main()`, and `config.attach_parent_console()` calls `AttachConsole(ATTACH_PARENT_PROCESS)` so output reaches the cmd window that launched it. `cli.main()` accepts an explicit argv, and the CLI's own `tray` branch passes an empty list because the two entry points would otherwise call each other until the stack ran out. Five tests in `tests/test_tray.py` cover bare invocation starting the tray, arguments reaching the CLI both explicitly and via `sys.argv`, the recursion guard, and `attach_parent_console()` being safe when not frozen.

Verified end to end through the real CLI in a subprocess with no environment override: auto-detection before configuring, a custom folder taking effect afterwards, the written JSON, rejection of a nonexistent path, reset back to auto-detection, and a corrupt settings file still allowing the CLI to run while reporting the problem. `tests/test_settings.py` adds 22 tests; suite 397 passed.

### RR-013 — Update “Open Last Report” only after completion

**Files:** `tenths/service/tray.py`, watcher/tray interface, tray tests.

Replace the current monkey-patch timing with an explicit processing-complete callback/event carrying `report_path`. Update `_last_report` only after the report exists. Keep `_find_latest_report()` as startup/fallback behavior.

**Acceptance criteria:** After a new session completes, Open Last Report opens that session; while processing, it never records a nonexistent or previous path as the new result.

**Resolution (2026-07-29), with RR-004.** `TelemetryWatcher` accepts `on_complete(report_path)` and calls it only after every required artifact exists. The tray supplies `_on_session_complete` and no longer monkey-patches `_on_file_ready`, so `_last_report` can no longer be set to a path that does not exist yet. `_start_watcher` also refuses to start a second watcher thread if one is alive. Verified end to end: the callback fired once, with the real report path.

### RR-014 — Remove machine state and local-data dependence from tests

**Files:** `tests/test_tray.py`, `tests/conftest.py`, related integration tests.

Required changes:

- Mock or abstract `winreg`; tests must never create/delete the real HKCU Run value.
- Replace the vacuous latest-report assertion with a temporary tree containing reports with controlled modification times.
- Stop relying solely on developer-local absolute telemetry paths.
- Use portable synthetic/recorded fixtures. Do not commit proprietary or personally identifying telemetry without explicit approval and rights review.
- Add a test-level guard where practical to prevent accidental access to production telemetry/registry state.

**Acceptance criteria:** The full suite produces no persistent machine changes and exercises the same behavior on a clean machine or CI runner.

**Resolution (2026-07-29) — machine safety done, portable .ibt fixtures still outstanding.**

Done:

- `tests/conftest.py` adds a `FakeRegistry` in-memory stand-in for the `winreg` subset `tray.py` uses, plus an **autouse** `_never_touch_real_registry` fixture that substitutes it for every test. No test can reach `HKCU`, including tests added later.
- `tests/test_tray.py` rewritten: registry behaviour is now asserted against the fake (value written, quoted command, round trip, absent-value delete, denied write, handle closing, Run-key path). The previously destructive `test_register_unregister_cycle` is gone.
- The vacuous report-lookup tests are replaced with temporary trees using controlled mtimes, covering newest-wins, nested `car/track/date/time` discovery, empty tree, and non-report files.
- `TELEMETRY_ARCHIVE` no longer hardcodes a developer path. It derives from the user profile and honours a `TENTHS_TEST_ARCHIVE` override.
- Tray tests grew from 8 to 22. Suite total 284.

Verified by planting a sentinel value under the real Run key, running the tray tests, and confirming it survived unchanged — the old test would have deleted it. Sentinel removed afterwards; the key is absent, as it was before.

**Synthetic telemetry (2026-07-29) — pipeline now verified on any machine.**

`tests/synthetic_ibt.py` writes a byte-valid `.ibt` that pyirsdk opens: header, `DiskSubHeader`, var headers, session-info YAML and sample rows, in native iRacing units. No real telemetry is committed, so no third-party names or customer IDs are exposed.

Its advantage over real files is **exact ground truth**. Corner apex speeds and lap times are dialled in, so the analyser can be asserted precisely instead of against loose ranges:

- Lap times recovered to the millisecond; valid laps, best lap and track length exact.
- Out-lap and in-lap correctly rejected by lap validity.
- Three corners driven identically report 0.000s loss and ~0 spread; the one inconsistent corner takes all the loss and a spread matching its configured speed range.
- A 120Hz variant proves sector timing uses the derived sample rate.
- `tests/test_pipeline_synthetic.py` — 35 tests covering parsing, lap detection, zone detection, min-speed metrics, loss attribution, summary JSON, HTML report and Markdown notes.

Clean-machine coverage went from 251 to 286 passing. Suite total 326.

**Regression value proven immediately.** A Qualcomm-like synthetic session (5409m, corners a few percent apart, every lap identical) failed on first run, exposing a genuine pre-existing defect: braking zones were split on a fixed 5% gap, which is 270m on that lap, so **T2 and T3 were merged into one 384m zone** and their combined time reported as T2. Fixed via `ZONE_GAP_METERS`; A/B confirmed Qualcomm 6 zones to 7 with T2/T3 separated and Winton unchanged.

**Committed real-telemetry fixtures (2026-07-29) — zero skips, RR-014 fully closed.**

The 33 archive-dependent tests now run everywhere. `tools/make_test_fixture.py` turns a real session into a committable fixture:

- **Identities removed.** An `.ibt` embeds the whole driver list — real names, customer IDs, abbreviations, initials, team names. The Winton race listed 12 people; no session in the archive was solo, since iRacing open practice lists everyone on the server. All identities become `Test Driver` / `UserID 0`, including the owner's, and `QualifyResultsInfo`, `CameraInfo`, `RadioInfo`, `SplitTimeInfo` and `CarSetup` are dropped. The tool refuses to write if its own audit finds a surviving identity.
- **Size reduced.** Only the ~52 channels the analyser reads are kept, plus 5 laps: 52 MB to 5.9 MB and 170 MB to 6.1 MB (12 MB committed in total).
- **Samples unmodified.** Lap times from the fixtures are identical to the originals, so these are genuinely real data for the laps retained.
- `.gitignore` needed an explicit `!tests/data/*.ibt` exception, since `*.ibt` is excluded.
- `tests/test_fixture_privacy.py` enforces the scrubbing on every run, so an unscrubbed fixture fails the suite before it can be published.
- `conftest.py` prefers the full archived session when present and falls back to the committed fixture, so the developer machine still exercises longer sessions.

Result: **343 tests pass with zero skips on both a clean checkout and the dev machine.** Two `test_summary` assertions that hardcoded "7 valid laps" now assert the actual contract — one entry per timed lap — which is a stronger test and no longer tied to one file.

### RR-015 — Make `TENTHS_TRACKS_DIR` a real override

**Files:** `tenths/track_map.py`, `tests/test_track_map.py`.

Place the environment directory first when configured, and search each candidate directory for the requested file rather than stopping at the first directory that merely exists. Preserve bundled landmark data as the primary general source unless the override contract explicitly includes replacing landmark records; document the exact precedence.

**Acceptance criteria:** A requested Markdown map in `TENTHS_TRACKS_DIR` is found even when built-in track directories exist and lack that file.

**Resolution (2026-07-30).**

Two separate bugs made the override useless, and fixing only one would not have helped.

1. `TENTHS_TRACKS_DIR` was appended after the built-in candidates, so a bundled directory always won.
2. The search stopped at the first candidate directory that merely *existed*, without checking whether it contained the requested file. Since a built-in directory always exists in a frozen build, the loop never reached any later candidate.

`_md_candidates_in()` now yields the candidate directories with the environment override first, and the lookup checks each directory for the specific file, continuing past directories that exist but lack it.

Precedence is documented as: bundled landmark data remains the primary general source for all 457 tracks; the `.md` lookup is a fallback for tracks with hand-authored maps; within that fallback, `TENTHS_TRACKS_DIR` outranks the bundled and repository `tracks/` directories. The override does not replace landmark records — that would be a different contract and was not implemented.

`tests/test_track_map.py` covers the override winning over a built-in directory that lacks the file, the override winning over one that has it, a nonexistent override being skipped without error, and fallback behavior with no override set.

### RR-016 — Reconcile the Summary corner-loss threshold

**Files:** `tenths/report.py`, `tests/test_summary_view.py`, `.kiro/specs/session-summary-view/{requirements,design,tasks}.md`.

Current Focus Card implementation/tests use `loss > 0.1s`; Requirements 4 and related design/tasks specify `loss > 0.3s` for the Time Loss Ranking. Next Race Focus has a separate formal fallback rule: when no `>0.3s` corner has a diagnosis, Requirement 9.3 selects the highest-loss corner generically, while Requirement 9.6 uses the all-within-target message only when all losses are nonpositive.

Obtain and document two product decisions separately:

1. The qualifying threshold for Time Loss Ranking/Focus Cards.
2. Whether to preserve or change the distinct Next Race Focus diagnosis and positive-loss fallback rules.

Then use named constants/rules and synchronize code, production tests, requirements, design, and tasks. Do not force one threshold across both features unless the formal fallback behavior is deliberately changed.

**Acceptance criteria:** The Focus Card threshold is identical in code, tests, requirements, design, and tasks. Next Race Focus independently follows its documented diagnosis/fallback rule, including the distinction between a positive sub-threshold loss and all losses being nonpositive.

**Resolution (2026-07-30) — owner decision recorded.**

Decision 1: the Focus Card qualifying threshold is **0.05s**, not the 0.3s in the original requirements. The owner's reasoning, which is correct and overrode my proposal of 0.3s: a genuinely fast driver may have only 0.23s recoverable across the whole lap, and a 0.3s gate would tell them everything is fine while real time is still on the table. The top-3 ranking is what limits noise, not the floor. The floor exists only to exclude corners where the driver was at or above their own reference.

Decision 2: the Next Race Focus diagnosis and positive-loss fallback rules are **preserved unchanged**. They are a deliberately different rule from the ranking gate and were not collapsed into it — the all-within-target message still requires all losses to be nonpositive, and a positive sub-threshold loss still yields a generic highest-loss selection rather than a clean bill of health.

The JavaScript filter is now `c.loss > 0.05` in a single place. The three duplicated corner-object builders were collapsed into one `buildCorner()` used by both the focus cards and Next Race Focus, so the two features cannot drift apart again — that duplication was how the thresholds diverged in the first place.

`tests/test_summary_view.py` asserts the 0.05s gate, the top-3 cap, that a 0.23s corner qualifies, and that the two Next Race Focus fallback branches remain distinguishable.

Remaining: the spec files under `.kiro/specs/session-summary-view/` still state 0.3s in Requirement 4. They are the original design intent rather than a live contract, and the decision above supersedes them; updating those documents is folded into RR-017.

### RR-017 — Correct user and developer documentation

**Files:** `README.md`, `docs/GETTING_STARTED.md`, `docs/HANDOFF.md`, `docs/TECH_DEBT.md`, `docs/DISTRIBUTION_READINESS.md`, architecture/report documents as applicable.

Corrections required:

- Remove or qualify full offline/self-contained claims until RR-009 is complete.
- Do not advertise a Browse Sessions tray action unless it is implemented; users currently open telemetry-root `index.html` directly.
- Describe the canonical `date/time` output layout only after RR-006 is complete.
- Do not promise every session is processed automatically until startup scan and retry behavior are complete.
- Correct missing-folder notification behavior after RR-012.
- Remove stale claims that landmark integration is not wired up.
- Remove unsupported landmark license assertions and defer to RR-001 notices.
- Keep test counts and completion status current or omit volatile counts.
- Do not mention unsupported product capabilities as complete.

**Acceptance criteria:** Every documented menu item, path, offline behavior, notification, and processing guarantee matches a tested production path.

### RR-018 — Define uninstall and data-retention policy

**Files:** `installer/tenths_setup.iss`, onboarding/release docs, installer tests.

Decide and document whether uninstall preserves reports, archived `.ibt` files, logs, and configuration. Review whether force-killing every process named `Tenths.exe` is acceptable or can be replaced by graceful shutdown plus bounded fallback. Do not delete user telemetry/report data without explicit informed policy.

**Acceptance criteria:** Installer UI/docs clearly state retained/deleted data, and install/uninstall testing verifies the policy.

**Observations added 2026-07-30 while building the installer** (still open, no decision made):

- Current `[UninstallDelete]` removes `{localappdata}\Tenths\logs` and `{localappdata}\Tenths\config`. The `config` directory **does not exist** — settings live at `{localappdata}\Tenths\settings.json`, a file, not a folder. So uninstall deletes a path that was never created and leaves the user's actual configuration behind. Decide whether settings should survive uninstall (defensible for reinstalls) and make the entry match reality either way.
- Reports and archived `.ibt` files live under `Documents\iRacing\telemetry` and are untouched by uninstall. That is almost certainly the right default, but it is currently accidental rather than stated.
- Inno Setup warns that the `[UninstallRun]` `taskkill /IM Tenths.exe /F` entry has no `RunOnceId`. The force-kill question from the original spec is still open; adding `RunOnceId` is a separate, smaller fix.

### RR-019 — Profile bundle composition and runtime resources

**Files:** `installer/tenths.spec`, build analysis output, packaging docs/tests.

The 2026-07-28 review build produced a roughly 90.4 MB bundle. Retained `build\tenths\Analysis-00.toc` confirms that pytest and extensive setuptools modules were collected; determine the import chain before excluding them rather than assuming pandas is the sole cause. The build console also emitted an optional `jinja2` hidden-import warning, but that warning is not present in the retained `warn-tenths.txt`, so reproduce and capture it before changing dependencies. Preserve `Analysis-00.toc`, `xref-tenths.html`, `warn-tenths.txt`, and exact future build logs as evidence. Remove only modules proven unnecessary. Measure idle tray RAM/CPU and processing impact before claiming a resource target.

**Acceptance criteria:** Bundle composition is documented, warning disposition is known, and measured idle/processing resource results support user-facing claims.

### RR-020 — Simplify frozen startup registration

**Files:** `tenths/service/tray.py`, startup tests.

The in-app command currently writes `"Tenths.exe" -m tenths.cli tray`. A frozen smoke test showed the app still launches, so this is not a proven blocker. Detect frozen mode and register only the quoted executable; retain `pythonw -m tenths.cli tray` for source mode. Test command construction without touching the real registry.

**Acceptance criteria:** Frozen and source startup commands are minimal, correctly quoted, and covered by isolated tests.

**Resolution (2026-07-30).**

`_startup_command()` checks `sys.frozen` and returns just the quoted executable path when frozen; the `-m tenths.cli tray` arguments were meaningless to a PyInstaller bootloader and only added a way for the command to be wrong. Source mode still returns `"pythonw" -m tenths.cli tray`.

Tested in `tests/test_tray.py` against the `FakeRegistry` from RR-014, so command construction is asserted without touching HKCU: frozen yields the quoted exe and nothing else, source yields the module invocation, and paths containing spaces stay quoted in both.

### RR-021 — Make the min-speed spread threshold speed-relative

**Files:** `tenths/report.py` (Summary View thresholds), `tenths/analyzer.py` constants, `tests/test_min_speed_spread.py`, `docs/COACHING_METRICS_DESIGN.md`.

**Status:** resolved 2026-07-30. The corner-attribution defects found on 2026-07-28 were fixed the same night (apex-centred windows, consistent outlier trimming, non-overlapping sectors, derived sample rate). The threshold itself was resolved separately — see the resolution below.

**Evidence:** On the Qualcomm race, 5 of 8 corners exceeded `min_speed_spread_mph > 10`. T13 reported a 14.9 mph spread at an 85.9 mph average apex speed. A fixed 10 mph band is a small fraction of a fast corner's speed but a large fraction of a slow one, so the threshold is far more sensitive on fast corners and produces low-value coaching.

**Required work:**

1. Decide whether spread qualifies on an absolute mph value, a percentage of apex speed, or a hybrid with a floor.
2. Apply the same decision to `apex_std_mph`, which has the identical scaling problem.
3. Validate on at least three sessions spanning slow street circuits and fast road courses, plus more than one car class.
4. Confirm that no more than a small minority of corners trigger on a clean, representative session.
5. Synchronize constants, Summary View thresholds, tests, and the coaching design document.

**Acceptance criteria:** On a representative clean session, spread-based diagnoses fire only where a driver would agree the corner is genuinely inconsistent, and the rule is documented with the sessions used to validate it.

**Do not** raise the threshold arbitrarily to reduce noise. Establish the scaling rule first.

**Resolution (2026-07-30) — hybrid percentage with a floor, validated on 8 real sessions.**

Decision: **a percentage of the corner's own apex speed, with an absolute floor.** The floor exists because a pure percentage collapses toward zero on a hairpin and would flag noise there.

Constants in `analyzer.py`, each `limit = max(fraction × reference_apex_speed, floor)`:

| Metric | Fraction | Floor |
|---|---|---|
| `min_speed_spread_mph` | 20% | 6.0 mph |
| `over_braking_mph` | 20% | 6.0 mph |
| `apex_std_mph` | 8% | 2.0 mph |

`apex_std_mph` got the same treatment, as the spec required — it has the identical scaling problem and a fixed band would have kept misfiring on fast corners after the spread rule was fixed. Each corner's computed limit is persisted alongside its measurement (`spread_limit_mph`, `over_braking_limit_mph`, `apex_std_limit_mph`) so the report compares against production values rather than re-deriving thresholds in JavaScript.

**Validation.** Ran production `analyze()` over 8 archived sessions: Winton National (2945 m, BMW M2 CS Racing), Summit Point (3197 m, BMW M2 G87), Mid-Ohio Full (3556 m, GT4), Lime Rock GP (2335 m, GT3), Road Atlanta (4056 m, GT3), Qualcomm/Coronado (5410 m, GT3), Road America (6413 m, GT3), Laguna Seca (3556 m, Porsche 992R). Four car models across GT3, GT4 and Generic profiles; track lengths spanning 2.3–6.4 km, which covers both the short technical and long fast cases the spec asked for.

Result across **41 corners**: 9 spread flags (22%), 4 apex-std flags (10%), 0 over-braking flags. Every flagged corner sits in the 36–83 mph apex band — the genuinely slow corners where inconsistency costs real time — rather than clustering on fast corners as before. On Qualcomm specifically the spread rule went from 5 of 8 corners to 2 of 7, and both survivors exceed their limit by a visible margin (12.6 vs 10.1, 9.9 vs 9.7) rather than by an artifact of scaling.

The two sessions excluded from the count returned no valid laps and were therefore not analysable: a short Fuji GT4 outing and a Charlotte oval ministock run. Neither is a threshold question, but oval lap validity is worth a separate look.

**One rule did not fire at all**, which the acceptance criteria did not anticipate. Over-braking peaked at 31% of its own limit across all 41 corners, so at 20% of apex speed it is roughly three times too high to ever trigger. That is an unvalidated rule rather than a passing one, and it is tracked as **RR-022** instead of being quietly counted as success here.

`tests/test_min_speed_spread.py` asserts the production constants and the `max(fraction × speed, floor)` shape, that a fast corner with a formerly-qualifying absolute spread no longer flags, that a slow corner at the floor still flags, and that each limit is present in the persisted output.

### RR-022 — The over-braking rule never fires and is therefore unvalidated

**Files:** `tenths/analyzer.py` (`OVER_BRAKING_LIMIT_FRACTION`, `OVER_BRAKING_LIMIT_FLOOR_MPH`), `tenths/report.py` Summary View, `tests/test_min_speed_spread.py`, `docs/COACHING_METRICS_DESIGN.md`.

**Severity:** Medium. Not a data-correctness defect — the measurement is right and nothing false is displayed. It is a coaching-value defect: a diagnosis that cannot trigger is dead weight that looks like working coverage.

**Opened by:** RR-021 validation, 2026-07-30.

**Evidence:** Across 41 corners in 8 archived sessions spanning four car models and 2.3–6.4 km tracks, `over_braking_mph` never exceeded its limit. Per-session peaks as a fraction of the limit were 30%, 4%, 13%, 20%, 13%, 22%, 31%, 23% — the highest observation anywhere was under a third of the trigger point.

**Root cause hypothesis, not yet confirmed:** `over_braking_mph` is best-lap minimum speed minus the trimmed average minimum speed. That is a difference between one lap and the central tendency of the same driver's laps, so its natural scale is much smaller than `min_speed_spread_mph`, which is the width of the whole band. Both were given 20% of apex speed. Reusing the spread fraction for a quantity with a different natural magnitude is the likely error.

**Required work:**

1. Confirm the distribution of `over_braking_mph` on real sessions before changing the constant. Do not tune it to make a specific session light up.
2. Decide whether the metric should be compared against the driver's own average at all, or against a reference such as the theoretical best or a prior PB — the current definition may be measuring something less coachable than intended.
3. If the metric is retained, derive the limit from the observed distribution and state the sessions used.
4. If it is not retained, remove it from the Summary View rather than leaving an inert diagnosis in the UI.
5. Keep `min_speed_spread_mph` unchanged; RR-021 validated it independently and it must not be re-tuned as a side effect.

**Required tests:** the chosen limit must be asserted against production constants, with at least one case that fires and one that does not, using values drawn from the measured distribution rather than invented ones.

**Acceptance criteria:** Either the over-braking diagnosis fires on corners where a driver would agree they are over-slowing, with the validating sessions documented, or it is removed from user-facing output.

## 6. Validation matrix

Run the smallest relevant tests while iterating, then the mandatory full suite after every code change.

```cmd
python -m pytest tests/ -v --tb=short
python -m compileall -q tenths
python -m pip check
```

Before declaring release readiness:

1. Run the full suite from a clean checkout on a machine without developer telemetry fixtures.
2. Confirm tests do not modify HKCU, startup entries, user telemetry, or external files.
3. Run lint, static typing, and dependency audit once tools are installed; document versions and results.
4. Generate reports for at least:
   - A PB session and a non-PB session with NumPy-derived values.
   - Two same-day sessions and a prior-day session at the same car/track.
   - GT3, GT4, Touring, and unknown/fallback class metadata.
   - Valid and partially malformed race results.
5. Open generated reports with networking disabled and inspect both views and browser console.
6. Build clean frozen artifacts and verify bundled data, notices, version metadata, and signatures.
7. Build the Inno installer and test clean install, launch, startup toggle, upgrade, and uninstall.
8. Measure idle and processing CPU/RAM on representative sim-racing hardware.
9. Re-read README and Getting Started against the actual installed application.
10. Verify `git diff --check` and inspect the complete diff before any requested commit.

## 7. Release gate checklist

Public distribution remains **NO-GO** until all applicable items are checked:

- [ ] RR-001 provenance and third-party notices approved.
- [x] RR-002 false-PB serialization fixed with NumPy production tests. Shared `tenths/jsonio.py` normalizer; `default=str` removed; unsupported types raise.
- [x] RR-003 progression works across nested dates and same-day sessions. Path-based current-session exclusion, strictly-earlier history filter, duplicate-layout dedupe.
- [x] RR-004 failures retry, notify, and log without stranding input. Rotating log at `%LOCALAPPDATA%\Tenths\logs\tenths.log`; 3 attempts with backoff; artifacts verified before archiving.
- [x] RR-005 startup scan processes files created while Tenths was stopped. `_scan_existing()` reuses the RR-004 claim path, so scan and event cannot double-process.
- [ ] RR-006 watcher and `process` produce complete per-session artifacts; standalone commands preserve their artifact-specific semantics in the canonical directory.
- [ ] RR-007 manual processing is isolated and archives only after success. **Deferred by owner** for beta; testers use the watcher.
- [x] RR-008 class labels/profiles use `.ibt` metadata. Display class and physics profile separated; `PROFILE_GENERIC` replaces "Touring"; slug-shaped class values rejected.
- [ ] RR-009 offline behavior and claims agree.
- [x] RR-010 race-result parsing tolerates bad fields/rows. All numeric fields via `_safe_int`; type-insensitive `_same_customer()`; non-dict rows filtered before sorting.
- [ ] RR-011 release artifacts carry metadata and approved signatures. **Metadata done**; signing, version single-sourcing, artifact-level assertion, and installer testing outstanding.
- [x] RR-012 first-run setup guidance is visible and actionable. Documents resolved via the Known Folder API, no decoy folder created, `settings.json` + `tenths config` for unusual layouts, one-time setup toast.
- [x] RR-013 tray receives the completed report path via `on_complete`.
- [x] RR-014 tests are portable and side-effect free. Registry isolated (verified with a sentinel); committed scrubbed telemetry fixtures give 343 passing with zero skips on a clean checkout.
- [x] RR-015 environment track-map override works as documented. Override placed first *and* each directory searched for the specific file.
- [x] RR-016 threshold decision is consistent across code/spec/tests. Focus Card floor set to **0.05s** by owner decision; Next Race Focus fallback rules preserved; `.kiro/specs` text update folded into RR-017.
- [ ] RR-017 all documentation matches production behavior.
- [ ] RR-018 uninstall/data retention is defined and tested.
- [ ] RR-019 bundle and runtime resource use are measured.
- [x] RR-020 startup command is cleaned up or explicitly deferred as low risk. Frozen mode registers the quoted exe only.
- [x] RR-021 spread threshold scales with corner speed and is validated on multiple tracks and car classes. Hybrid percentage-with-floor; 9 of 41 corners flag across 8 sessions, 4 car models, 2.3–6.4 km.
- [ ] RR-022 over-braking rule fires meaningfully or is removed from user-facing output.
- [ ] Full clean-machine validation and installer matrix pass.

## 8. Evidence map

Primary implementation locations:

- JSON normalization: `tenths/jsonio.py`
- Logging: `tenths/applog.py`
- Settings and path resolution: `tenths/config.py`
- JSON/progression: `tenths/summary.py`
- HTML data and remote assets: `tenths/report.py`
- Watcher output/retry/startup behavior: `tenths/service/watcher.py`
- Tray startup/latest report: `tenths/service/tray.py`
- Manual grouping/archive behavior: `tenths/process.py`
- Class metadata/detection: `tenths/analyzer.py`
- Result conversion/matching: `tenths/results.py`
- Track override precedence: `tenths/track_map.py`
- Frozen resources/console/metadata: `installer/tenths.spec`
- Installer startup/uninstall: `installer/tenths_setup.iss`
- Progression layout tests: `tests/test_progression.py`
- Registry side effects: `tests/test_tray.py`
- Summary threshold: `tests/test_summary_view.py` and `.kiro/specs/session-summary-view/`

Confirmed examples at review time included persisted summaries with `"is_new_pb": "False"` under the telemetry workspace. These are evidence, not test fixtures; do not modify user telemetry during remediation.

## 9. Status update protocol

When resolving an item:

1. Change its table/status entry only after implementation and required validation pass.
2. Add a short `Resolution` paragraph under the issue naming changed files, tests, and any deliberate deviation from this plan.
3. Record unresolved human decisions explicitly; do not silently guess licensing, threshold, retention, or signing policy.
4. Keep issue IDs stable so future models and commit messages can refer to them.
5. If implementation reveals a new release risk, add a new ID rather than hiding it inside an unrelated issue.

A green unit suite alone is not sufficient for release. Public readiness requires legal provenance, artifact-level packaging checks, offline browser verification, clean-machine installer testing, and accurate documentation.