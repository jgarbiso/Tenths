# Distribution Readiness Review

Senior developer review conducted 2026-07-28, with the lens: *"another sim racer downloads the installer and starts using it."*

The architecture is solid (clean separation, event-driven watcher, 204 tests, schema migrations). The blockers below are single-machine / single-account assumptions that would make the app misbehave silently for anyone who isn't the original developer.

**Severity legend:** 🔴 Critical (breaks/silently fails for new users) · 🟠 High · 🟡 Medium · 🟢 Polish

---

## 🔴 Critical — must fix before sharing

### D1 — Hardcoded iRacing customer ID
- **Location:** `results.py:19` → `MY_CUST_ID = 1434150  # Justin Garbiso`
- **Impact:** All race-result matching keys off this constant. For any other user, `my_result` is always `None` — race badge, finish position, iRating delta, and race notifications silently never appear. The single biggest distribution defect.
- **Fix:** Derive the driver's cust_id from the .ibt session_info (`DriverInfo.DriverUserID` / `DriverInfo.Drivers[CarIdx==PlayerCarIdx]`). Fall back to a config/env override. Never hardcode.
- **Status:** ✅ FIXED (2026-07-28) — `parse_result(filepath, my_cust_id=...)` now takes the driver's cust_id; all 4 call sites pass `si.get('driver_id')` (already extracted by analyzer). Constant removed. Tests: TestD1_NoHardcodedCustId.

### D2 — Watcher silently dies if telemetry folder is missing
- **Location:** `config._find_iracing_telemetry()` returns a non-existent path; `watcher.start()` → `observer.schedule()` raises inside the daemon thread.
- **Impact:** On a fresh PC or a machine where iRacing telemetry isn't enabled yet, the tray icon appears alive but nothing works. No error surfaced to the user.
- **Fix:** Guard `watcher.start()` — if the root doesn't exist, create it or show a toast ("iRacing telemetry folder not found — enable telemetry in iRacing, then restart Tenths") instead of dying silently.
- **Status:** ✅ FIXED (2026-07-28) — `_ensure_watch_root()` creates the folder if possible, else prints + shows an error toast and returns cleanly. Tests: TestD2_WatcherFolderGuard.

### D3 — `tenths incident` command crashes
- **Location:** `incidents.py` has no `main()`; it's a bare script reading `sys.argv` at import. `cli.py` does `from tenths.incidents import main` → ImportError.
- **Impact:** Any user running the documented `incident` command crashes the app.
- **Fix:** Wrap `incidents.py` logic in a `main()` function (like the other modules) or remove the CLI command if it's not ready for users.
- **Status:** ✅ FIXED (2026-07-28) — rewrote `incidents.py` with `analyze_incidents()` + `main()`, added file-open error handling and lap-arg validation. Verified end-to-end against a real .ibt. Tests: TestD3_IncidentsMain.

### D4 — PyYAML missing from dependencies
- **Location:** `pyproject.toml` dependencies list; `analyzer.py` imports `yaml`.
- **Impact:** `pip install` from source fails at runtime with ImportError. (Frozen exe is fine — PyInstaller bundles it via the spec's hidden import.)
- **Fix:** Add `PyYAML>=6.0,<7.0` to `pyproject.toml` dependencies.
- **Status:** ✅ FIXED (2026-07-28) — added `PyYAML>=6.0,<7.0`. Tests: TestD4_PyYamlDependency.

---

### D12 — Unicode console crash on stock Windows consoles (found during D3 verification)
- **Location:** Any stdout print of `→`, `✓`, `°`, etc. The Windows console defaults to cp1252, which can't encode these → `UnicodeEncodeError`. Surfaced in `incidents.py` output but affects `process`/`watch` too.
- **Impact:** A new user on a stock console could crash mid-output (e.g., the incident forensics command crashed on the `→` in a speed-drop line).
- **Fix:** `config.configure_console()` reconfigures stdout/stderr to UTF-8 (errors='replace'), called from every entry point (`cli.main`, `process.main`, `tray.main`). Guarded for frozen/no-console (stdout None).
- **Status:** ✅ FIXED (2026-07-28) — Tests: TestConsoleUtf8Safe. Verified incident command runs clean (exit 0).

---

## 🟠 High priority

### D5 — In-app "Start with Windows" writes a broken command for the frozen exe
- **Location:** `tray._register_startup` → `sys.executable.replace('python.exe','pythonw.exe')`
- **Impact:** In a frozen build `sys.executable` is `Tenths.exe`, so the registered command becomes `Tenths.exe -m tenths.cli tray`, which the frozen entry ignores. The Inno installer's Run key is correct, so this only affects users who toggle the in-app option.
- **Fix:** Detect frozen mode — register `"{Tenths.exe}"` with no `-m` args when frozen; use pythonw only when running from source.
- **Status:** OPEN

### D6 — Failed sessions in watch mode are lost
- **Location:** `watcher._process_file` catches all exceptions but the file is already in `self._processed`, is not archived, and `notifier.notify_error()` (which exists) is never wired up.
- **Impact:** A processing failure produces silence — no retry that session, no error toast, file stranded in the watch dir.
- **Fix:** On failure, call `notify_error`, and do NOT keep the file in `_processed` (or move to a `_failed/` dir) so it can be retried.
- **Status:** OPEN

### D7 — No user-facing documentation
- **Location:** All nine `docs/*.md` are developer-facing; README has personal paths and `python -m` invocations.
- **Impact:** A user who installs the exe has no getting-started: how to enable iRacing telemetry, what the tray icon does, where reports land.
- **Fix:** Add a user-facing getting-started (in README or a `docs/GETTING_STARTED.md`): install, enable telemetry, first session, where to find reports, tray menu overview.
- **Status:** ✅ FIXED (2026-07-28) — created `docs/GETTING_STARTED.md` (install → enable telemetry via Alt+L or `irsdkLogAll=1` → drive → read report → tray menu → troubleshooting). Rewrote `README.md` to lead with the driver story and link the guide; developer content moved to a clearly separated section. Tray menu documented to match the actual menu (Open Last Report / Pause Processing / Start with Windows / Exit).

### D8 — `process` batch crashes on one bad file
- **Location:** `process.py main` does not wrap `analyze()`; `results.parse_csv_result` indexes `lines[0]/[1]` with no length check.
- **Impact:** A single malformed/truncated .ibt or short CSV kills the whole batch (the watcher wraps this, the CLI batch does not).
- **Fix:** Wrap per-file analysis in try/except in `process.main`; length-check before indexing in `parse_csv_result`.
- **Status:** OPEN

---

## 🟡 Medium

### D9 — GT4 detection is a hardcoded car list
- **Location:** `analyzer.py:44` → `GT4_CARS = [...]`
- **Impact:** Any GT4 not in the list silently gets "Touring" physics and wrong diagnostics. Conflicts with the goal of supporting all car types.
- **Fix:** Detect car class from the .ibt `CarClassShortName` / `CarScreenName` rather than a literal list, or expand the list and fall back on class metadata.
- **Status:** OPEN

### D10 — Integration tests only run on the developer's machine
- **Location:** `conftest.py` → `TELEMETRY_ARCHIVE = r"c:\Users\justi\...\_archive"` with two specific files.
- **Impact:** The entire .ibt→analysis→report pipeline is unverified on any other machine or CI. No regression safety net for parsing.
- **Fix:** Commit one small anonymized/sample .ibt (or a recorded fixture) to the repo so integration tests run anywhere. Alternatively, add a synthetic .ibt builder.
- **Status:** OPEN

### D11 — Missing test coverage for known-broken paths
- **Impact:** No test for `incidents.py` (would have caught D3), no test for the missing-telemetry-folder path (D2), no test that race-result matching works for a non-developer cust_id (D1).
- **Fix:** Add tests alongside the D1/D2/D3 fixes.
- **Status:** OPEN

---

## 🟢 What's genuinely good (keep)

- Watcher resource design: event-driven watchdog, BELOW_NORMAL priority, lazy imports, ~zero idle CPU
- Frozen-path resolution (`sys._MEIPASS`) for bundled data, verified via real PyInstaller build
- Schema versioning + migration system
- MIT license present; versions consistent across pyproject/init/config; dependencies otherwise well-pinned
- First-session and unknown-track handling degrade gracefully
- Inno installer is clean: per-user, no admin, proper uninstall + taskkill

---

## Recommended fix order

1. **D1–D4** (critical correctness) — small, contained fixes with tests
2. **D7** (user getting-started doc)
3. **D5, D6, D8** (robustness)
4. **D9–D11** (breadth + test hardening)
