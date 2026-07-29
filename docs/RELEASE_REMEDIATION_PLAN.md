# Tenths Release Remediation Plan

**Status:** Active source of truth  
**Review date:** 2026-07-28  
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
| RR-002 | Release blocker | NumPy values serialize as strings and cause false PB badges | None |
| RR-003 | Release blocker | Progression cannot traverse canonical date/time session layout | RR-006 stage A path helper |
| RR-004 | Release blocker | Watcher failures are silent, permanent, and not retried | RR-006 artifact transaction contract |
| RR-005 | Release blocker | Watcher misses files present at startup | RR-004 state model |
| RR-006 | Release blocker | Manual processing emits one representative report per day | None |
| RR-007 | High | Manual processing is not failure-isolated or transactional | RR-006 |
| RR-008 | High | GT3 and most cars are mislabeled as Touring | None |
| RR-009 | High | Detailed report is not offline despite product claims | RR-001 if assets are bundled |
| RR-010 | High | Race-result parsing aborts on malformed row values | None |
| RR-011 | High | Executable is unsigned and lacks metadata | Release credentials for signing |
| RR-012 | Medium | First-run telemetry guidance is ineffective | RR-004/RR-005 |
| RR-013 | Medium | Tray tracks the latest report before processing completes | RR-004 completion signal |
| RR-014 | Execution prerequisite | Tests mutate HKCU and depend on developer-local data | None; resolve before other code work |
| RR-015 | Medium | `TENTHS_TRACKS_DIR` is shadowed by built-in directories | None |
| RR-016 | Medium | Summary threshold differs between specs and implementation | Product decisions |
| RR-017 | Medium | User documentation contains incorrect feature/behavior claims | Functional fixes above |
| RR-018 | Medium | Uninstall retention and process-kill policy is undocumented | Product decision |
| RR-019 | Low | Bundle size and hidden imports need profiling | Functional blockers first |
| RR-020 | Low | Frozen startup command has unnecessary CLI arguments | None; not a startup blocker |

Recommended batches:

0. **Safe test prerequisite:** RR-014. Fix the registry test first; after that change, the mandatory full suite will exercise the isolated replacement rather than the destructive test.
1. **Legal gate:** RR-001 can proceed independently and may require human verification.
2. **Canonical paths:** RR-006 stage A introduces the shared output-path helper and command-specific artifact contract.
3. **Data correctness:** RR-002 and RR-003.
4. **Pipeline durability:** finish RR-006, then RR-004, RR-005, RR-007, RR-012, and RR-013.
5. **Analysis/report correctness:** RR-008 through RR-010 and RR-016.
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

### RR-003 — Make progression understand nested per-session history

**Files:** `tenths/summary.py`, `tenths/process.py` baseline lookup, `tests/test_progression.py`.

**Root cause:** `compute_progression()` assumes `session_dir` is the date folder and scans only direct sibling directories. Watcher output passes a time folder, causing the function to scan only sibling times under the current date and miss prior dates.

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

### RR-012 — Provide effective first-run telemetry guidance

**Files:** `tenths/config.py`, `tenths/service/watcher.py`, notifier/onboarding tests and docs.

Creating a missing telemetry folder currently looks like success, even when iRacing telemetry is disabled. Add a one-time, actionable first-run state that explains Alt+L/`irsdkLogAll=1`, the watched path, and how Tenths detects a first file. Do not repeatedly nag established users. Test the newly created empty-root path separately from filesystem creation failure.

**Acceptance criteria:** A new user cannot sit indefinitely with a healthy-looking tray app and no explanation of how to produce telemetry.

### RR-013 — Update “Open Last Report” only after completion

**Files:** `tenths/service/tray.py`, watcher/tray interface, tray tests.

Replace the current monkey-patch timing with an explicit processing-complete callback/event carrying `report_path`. Update `_last_report` only after the report exists. Keep `_find_latest_report()` as startup/fallback behavior.

**Acceptance criteria:** After a new session completes, Open Last Report opens that session; while processing, it never records a nonexistent or previous path as the new result.

### RR-014 — Remove machine state and local-data dependence from tests

**Files:** `tests/test_tray.py`, `tests/conftest.py`, related integration tests.

Required changes:

- Mock or abstract `winreg`; tests must never create/delete the real HKCU Run value.
- Replace the vacuous latest-report assertion with a temporary tree containing reports with controlled modification times.
- Stop relying solely on developer-local absolute telemetry paths.
- Use portable synthetic/recorded fixtures. Do not commit proprietary or personally identifying telemetry without explicit approval and rights review.
- Add a test-level guard where practical to prevent accidental access to production telemetry/registry state.

**Acceptance criteria:** The full suite produces no persistent machine changes and exercises the same behavior on a clean machine or CI runner.

### RR-015 — Make `TENTHS_TRACKS_DIR` a real override

**Files:** `tenths/track_map.py`, `tests/test_track_map.py`.

Place the environment directory first when configured, and search each candidate directory for the requested file rather than stopping at the first directory that merely exists. Preserve bundled landmark data as the primary general source unless the override contract explicitly includes replacing landmark records; document the exact precedence.

**Acceptance criteria:** A requested Markdown map in `TENTHS_TRACKS_DIR` is found even when built-in track directories exist and lack that file.

### RR-016 — Reconcile the Summary corner-loss threshold

**Files:** `tenths/report.py`, `tests/test_summary_view.py`, `.kiro/specs/session-summary-view/{requirements,design,tasks}.md`.

Current Focus Card implementation/tests use `loss > 0.1s`; Requirements 4 and related design/tasks specify `loss > 0.3s` for the Time Loss Ranking. Next Race Focus has a separate formal fallback rule: when no `>0.3s` corner has a diagnosis, Requirement 9.3 selects the highest-loss corner generically, while Requirement 9.6 uses the all-within-target message only when all losses are nonpositive.

Obtain and document two product decisions separately:

1. The qualifying threshold for Time Loss Ranking/Focus Cards.
2. Whether to preserve or change the distinct Next Race Focus diagnosis and positive-loss fallback rules.

Then use named constants/rules and synchronize code, production tests, requirements, design, and tasks. Do not force one threshold across both features unless the formal fallback behavior is deliberately changed.

**Acceptance criteria:** The Focus Card threshold is identical in code, tests, requirements, design, and tasks. Next Race Focus independently follows its documented diagnosis/fallback rule, including the distinction between a positive sub-threshold loss and all losses being nonpositive.

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

### RR-019 — Profile bundle composition and runtime resources

**Files:** `installer/tenths.spec`, build analysis output, packaging docs/tests.

The 2026-07-28 review build produced a roughly 90.4 MB bundle. Retained `build\tenths\Analysis-00.toc` confirms that pytest and extensive setuptools modules were collected; determine the import chain before excluding them rather than assuming pandas is the sole cause. The build console also emitted an optional `jinja2` hidden-import warning, but that warning is not present in the retained `warn-tenths.txt`, so reproduce and capture it before changing dependencies. Preserve `Analysis-00.toc`, `xref-tenths.html`, `warn-tenths.txt`, and exact future build logs as evidence. Remove only modules proven unnecessary. Measure idle tray RAM/CPU and processing impact before claiming a resource target.

**Acceptance criteria:** Bundle composition is documented, warning disposition is known, and measured idle/processing resource results support user-facing claims.

### RR-020 — Simplify frozen startup registration

**Files:** `tenths/service/tray.py`, startup tests.

The in-app command currently writes `"Tenths.exe" -m tenths.cli tray`. A frozen smoke test showed the app still launches, so this is not a proven blocker. Detect frozen mode and register only the quoted executable; retain `pythonw -m tenths.cli tray` for source mode. Test command construction without touching the real registry.

**Acceptance criteria:** Frozen and source startup commands are minimal, correctly quoted, and covered by isolated tests.

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
- [ ] RR-002 false-PB serialization fixed with NumPy production tests.
- [ ] RR-003 progression works across nested dates and same-day sessions.
- [ ] RR-004 failures retry, notify, and log without stranding input.
- [ ] RR-005 startup scan processes files created while Tenths was stopped.
- [ ] RR-006 watcher and `process` produce complete per-session artifacts; standalone commands preserve their artifact-specific semantics in the canonical directory.
- [ ] RR-007 manual processing is isolated and archives only after success.
- [ ] RR-008 class labels/profiles use `.ibt` metadata.
- [ ] RR-009 offline behavior and claims agree.
- [ ] RR-010 race-result parsing tolerates bad fields/rows.
- [ ] RR-011 release artifacts carry metadata and approved signatures.
- [ ] RR-012 first-run setup guidance is visible and actionable.
- [ ] RR-013 tray receives the completed report path.
- [ ] RR-014 tests are portable and side-effect free.
- [ ] RR-015 environment track-map override works as documented.
- [ ] RR-016 threshold decision is consistent across code/spec/tests.
- [ ] RR-017 all documentation matches production behavior.
- [ ] RR-018 uninstall/data retention is defined and tested.
- [ ] RR-019 bundle and runtime resource use are measured.
- [ ] RR-020 startup command is cleaned up or explicitly deferred as low risk.
- [ ] Full clean-machine validation and installer matrix pass.

## 8. Evidence map

Primary implementation locations:

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