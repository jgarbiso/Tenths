# Tenths — Outstanding Issues Worklog (HISTORICAL — DO NOT EXECUTE)

> ## STOP. This document is a historical record, not a work queue.
>
> **Do not execute any task in this file.** It was written on 2026-07-30 against
> commit `d2c16a8` as a build sheet for 9 open issues. Eight of those nine are now
> resolved and the ninth is deliberately deferred. Acting on the instructions
> below would re-do finished work or revert current behaviour.
>
> **Status as of 2026-08-07:** 22 of 23 issues resolved. The only open item is
> **RR-011**, and only its code-signing half — version metadata is done, signing
> is deferred to `docs/POST_MVP.md` and is not a beta blocker. `v0.9.0-beta.2` is
> released and the repo is public.
>
> | Issue in this file | Actual status |
> |---|---|
> | RR-001 landmark provenance | Resolved — data is MIT, see `THIRD_PARTY_NOTICES.md` |
> | RR-006 per-session artifacts | Resolved |
> | RR-007 isolate manual failures | Resolved |
> | RR-009 Detailed report offline | Resolved — Option A, assets inlined |
> | RR-011 artifact metadata + signing | **Metadata done; signing deferred** |
> | RR-017 docs match production | Resolved |
> | RR-018 uninstall / data retention | Resolved |
> | RR-019 bundle size | Resolved — measured in `docs/PACKAGING.md` |
> | RR-022 over-braking never fires | Resolved — retuned to 7% / 1.5 mph |
>
> **Facts in this file that are now wrong.** Do not rely on any figure here
> without re-measuring:
> - The test baseline is quoted as **467**. It is **595**.
> - The bundle is quoted at **90.5 MB**. It is **85.5 MB**.
> - The threshold constants are named `SPREAD_LIMIT_FLOOR_MPH`,
>   `OVER_BRAKING_LIMIT_FLOOR_MPH` and `APEX_STD_LIMIT_FLOOR_MPH`. Those names no
>   longer exist. The analyzer now stores SI, and they are
>   `SPREAD_LIMIT_FLOOR_MPS`, `OVER_BRAKING_LIMIT_FLOOR_MPS` and
>   `APEX_STD_LIMIT_FLOOR_MPS`, expressed as `mph_to_mps(...)` of the same
>   calibrated values.
> - `OVER_BRAKING_LIMIT_FRACTION` is quoted as `0.20`. It is `0.07`.
>
> **Where the truth lives instead:**
> - `docs/RELEASE_REMEDIATION_PLAN.md` — the authoritative issue list with a
>   resolution paragraph per item and the release-gate checklist.
> - `docs/POST_MVP.md` — everything deliberately deferred, including code signing.
> - `.kiro/steering/tenths-development.md` — the standards that currently apply.
> - The test suite — the only executable statement of current behaviour.
>
> **Why it is kept.** Sections 0 (working rules) and 1 (environment, commands,
> the report-inspection and JavaScript-verification procedures) are still
> accurate and useful, and the per-issue root-cause analysis explains *why*
> decisions were made. Read it for background; take instructions from the
> documents listed above.

**Everything below this line is preserved as written on 2026-07-30.**

---

**Purpose:** This is a build sheet for the 9 issues still open before public release. Every task below is written to be executed without prior knowledge of the project and without re-deriving facts. All measurements quoted here were taken on 2026-07-30 against commit `d2c16a8`.

**Companion document:** `docs/RELEASE_REMEDIATION_PLAN.md` holds the original review, the full issue specifications, and the Resolution paragraphs for the 11 issues already fixed. Read the matching section there before starting an issue. This file tells you *what to do*; that file tells you *why it was ruled a defect*.

**Do not use** `docs/DISTRIBUTION_READINESS.md` or `docs/HANDOFF.md`. They are marked historical and describe behavior that has since changed.

---

## 0. Rules you must follow

These are not suggestions. Violating any of them means the work has to be redone.

1. **Run the full test suite after every code change**, from the repo root:
   ```cmd
   python -m pytest tests/ -v --tb=short
   ```
   The baseline is **467 passed, 0 failed, 0 skipped**. If your change lowers the pass count or introduces a skip, you are not finished.
2. **Never delete, skip, weaken, or `xfail` a test to make a change pass.** If a test now contradicts intended behavior, change the test to assert the *new* behavior and say so in your report. If you cannot tell which is right, stop and ask.
3. **No `assert True`, no vacuous tests.** Every test must assert a specific value, type, or condition. A test that would still pass if the feature were deleted is worthless.
4. **Tests must call production functions**, not re-implement their logic. Copying a formula into a test proves only that you can copy a formula.
5. **Do not commit** unless the owner explicitly asks. Do not amend or force-push.
6. **Do not modify the real Windows registry.** `tests/conftest.py` has an autouse `_never_touch_real_registry` fixture; leave it in place.
7. **Do not modify anything under the owner's telemetry directory.** It contains other drivers' names and customer IDs. Read it if you need evidence; never write to it.
8. **Do not commit telemetry data** to the parent `Sim` repo. If you commit there, stage only the `Tenths` submodule pointer: `git add Tenths`.
9. **Use `webbrowser.open()`** for anything that opens a browser. Never hardcode Chrome or any browser path.
10. **Delete any temporary script you create** once you have used it. Do not leave scratch files in the repo.
11. **When editing JavaScript inside `tenths/report.py`**, Python will not catch your syntax errors. See section 1.4 for the required verification procedure.
12. **Decisions marked OWNER DECISION REQUIRED are not yours to make.** Do not guess a licensing conclusion, a threshold, or a data-retention policy. Stop and ask.

---

## 1. Environment and commands

### 1.1 Paths

| What | Path |
|---|---|
| Repo root (run all commands here) | `<repo-root>` |
| Parent repo (Tenths is a submodule) | `<repo-root>/..` |
| Owner's real telemetry (read-only to you) | `<Documents>/iRacing/telemetry` |
| Archived `.ibt` source files for evidence | `<Documents>/iRacing/telemetry/_archive` |
| Committed test fixtures (safe, scrubbed) | `Tenths\tests\data\*.ibt` |
| Build output | `Tenths\dist\Tenths\` |
| Installer output | `Tenths\installer\Output\TenthsSetup.exe` |

Python is 3.14.5. The shell is `cmd`; the command separator is `&`, not `&&`.

### 1.2 Commands you will need

```cmd
python -m pytest tests/ -v --tb=short          :: full suite, mandatory after every change
python -m pytest tests/test_unit.py            :: fast subset while iterating
python -m pytest -k "over_braking"             :: run by keyword
python -m compileall -q tenths                 :: syntax check the package
python installer/build.py                      :: build dist/Tenths/Tenths.exe
python installer/build.py --full               :: build exe + TenthsSetup.exe
```

Inno Setup 6 **is** installed at `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`. To rebuild only the installer without redoing PyInstaller:

```cmd
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\tenths_setup.iss
```

### 1.3 Generating a real report for manual inspection

Several tasks need you to look at an actual report. Use a committed fixture so you never touch the owner's telemetry:

```cmd
python -m tenths.cli report "tests\data\bmwm4evogt4_midohio full 2026-06-02 20-48-57.ibt"
```

Two committed fixtures are available, both scrubbed of driver identities and trimmed to 5 laps:

```
tests\data\bmwm2csr_winton national 2026-06-06 22-26-36.ibt     5.9 MB
tests\data\bmwm4evogt4_midohio full 2026-06-02 20-48-57.ibt     6.1 MB
```

`tests/test_fixture_privacy.py` enforces the scrubbing on every run. If you create a new fixture, use `tools/make_test_fixture.py` — never commit a raw `.ibt`, because it embeds the full driver list including real names and customer IDs.

### 1.4 Mandatory procedure for JavaScript changes in `report.py`

`tenths/report.py` builds the report's JavaScript as a Python string inside `_get_js()`. Python will happily compile a file containing broken JavaScript, and the suite will pass while the report is silently dead in the browser. Every time you touch that string:

1. Regenerate a report (section 1.3).
2. Open it in the default browser.
3. Press **F12** and read the Console tab. **Zero errors is the requirement.**
4. Click both the **Summary** and **Detailed** tabs and confirm each renders.
5. State in your report that you did this and what the console showed.

Watch for: unbalanced braces, and `${}` template placeholders. Those use backticks and are JavaScript, not Python f-strings.

---

## 2. Which task to do next

Dependencies are real. Doing these out of order will cause rework.

```
RR-017 (docs)          ── no dependencies ── START HERE
RR-022 (over-braking)  ── no dependencies
RR-011 (version+test)  ── no dependencies
RR-018 (uninstall)     ── needs OWNER DECISION
RR-019 (bundle)        ── no dependencies, measurement only
RR-009 (offline)       ── needs OWNER DECISION (Option A or B)
RR-006 (per-session)   ── biggest change; do after the above
RR-007 (batch safety)  ── BLOCKED until RR-006 is done
RR-001 (licensing)     ── needs the OWNER/legal; you can only prepare
```

Recommended order: **RR-017 → RR-022 → RR-011 → RR-019 → RR-018 → RR-009 → RR-006 → RR-007 → RR-001.**

RR-017 is first because two of its statements are now actively false in a way that undersells finished work, and because it is pure text with no risk of breaking the build. RR-006 is last among the code tasks because it is the largest and will conflict with anything else touching output paths.

### Status summary

| ID | Severity | One-line | Blocked by |
|---|---|---|---|
| RR-001 | Release gate | Landmark dataset provenance and third-party notices | Owner / legal |
| RR-006 | Release blocker | Manual `process` writes one report per day, not per session | — |
| RR-007 | High | Manual `process` archives before writing output; one bad file aborts the batch | RR-006 |
| RR-009 | High | Detailed report loads fonts, Leaflet, and Chart.js from CDNs | Owner decision |
| RR-011 | High | Version duplicated in 3 files; no test reads the built EXE; installer never install-tested | Certificate for signing |
| RR-017 | Medium | Two docs claim resolved issues are still broken | — |
| RR-018 | Medium | Uninstall deletes a folder that never existed and leaves settings behind | Owner decision |
| RR-019 | Low | 90.5 MB bundle unexplained; original cause hypothesis is wrong | — |
| RR-022 | Medium | Over-braking diagnosis can never fire; a second hardcoded threshold contradicts it | — |

---

## RR-017 — Correct documentation that contradicts production behavior

**Severity:** Medium. **Blocked by:** nothing. **Estimated scope:** text only, no code.

### Why this matters

Earlier sessions correctly added "this is a known release blocker" caveats to the user docs. Several of those blockers have since been fixed, and the caveats were not removed. The docs now tell a beta tester that working features are broken. A tester who reads "files created while Tenths was stopped are not recovered" will manually work around a problem that no longer exists, and will not report it when it breaks again.

### Exact defects, with line numbers

These are the confirmed inaccuracies. Verify each line still says this before editing; line numbers drift.

**1. `README.md` line 45** — claims startup recovery and retry are unfinished. Both are done (RR-004 and RR-005, resolved 2026-07-29 and 2026-07-30).

> Current: `- **Low-friction** — while Tenths is running, it watches for completed sessions and processes them automatically; startup recovery and retry handling are tracked release blockers`

Replace the caveat with what actually happens: the watcher scans for existing `.ibt` files when it starts, and retries a failed session 3 times with backoff before notifying the user and leaving the file in place.

**2. `docs/GETTING_STARTED.md` line 52** — same defect, stated more explicitly.

> Current: `Files created while Tenths is stopped are not yet recovered automatically on startup; this is a documented release blocker.`

This is false. `TelemetryWatcher._scan_existing()` handles exactly this case. Replace with a plain statement that Tenths picks up sessions recorded while it was closed, the next time it starts.

**3. `README.md` line 98 and `docs/GETTING_STARTED.md` line 107** — both correctly say manual CLI output is inconsistent. **Leave these alone.** RR-006 is still open, so these statements are true. Revisit them only as part of RR-006.

### What to verify rather than assume

Do not trust this list to be complete. Check each of the following claims against the code and fix any that do not match. For each one, name the file and function you checked.

| Claim to check | Where to verify it |
|---|---|
| Every documented tray menu item exists | `tenths/service/tray.py`, the menu construction in `TenthsTray` |
| The described output folder layout matches what is written | `tenths/service/watcher.py` line ~576 |
| Notification behavior on a missing telemetry folder | `tenths/service/watcher.py` `_ensure_watch_root()` and `_check_first_run()` |
| Any stated test count | run the suite; it is 467 |
| Any claim that landmark integration is "not wired up" | `tenths/track_map.py` — it is wired up and is the primary source |
| Any license assertion about the landmark data | must say nothing definite; see RR-001 |
| Physics coaching claims | `tenths/analyzer.py` `detect_physics_profile()` — only GT4 and Generic exist |

Also check `docs/TECH_DEBT.md` for stale entries describing now-fixed issues.

### Definition of done

- [ ] No document states that a resolved issue is still broken.
- [ ] No document states that an unresolved issue is fixed.
- [ ] Every menu item, path, notification, and processing guarantee named in `README.md` and `docs/GETTING_STARTED.md` corresponds to code you have located.
- [ ] Volatile numbers (test counts) are either current or removed.
- [ ] `docs/BETA_TESTING.md` still matches reality — it was verified accurate on 2026-07-30, so if you change behavior anywhere, re-check it.
- [ ] Full suite still passes at 467. Documentation changes should not affect it; if the count changes, something else went wrong.

### Do not

- Do not remove the RR-006 caveats about manual CLI output. They are still true.
- Do not add new feature claims. Your job is to make existing claims accurate, not to advertise.

---

## RR-022 — The over-braking diagnosis can never fire

**Severity:** Medium. **Blocked by:** nothing. **Opened:** 2026-07-30 during RR-021 validation.

### Why this matters

This is not a wrong-number bug. The measurement is correct and nothing false is shown to the user. The problem is that one of the coaching system's diagnosis branches is unreachable, so the product looks like it covers over-slowing when it does not. There is also a second, contradictory threshold hardcoded in the report.

### Evidence already gathered — do not redo this

Production `analyze()` was run over 8 archived sessions covering 4 car models and tracks from 2,335 m to 6,413 m. Across **41 corners, `over_braking_mph` exceeded its limit zero times.** Per-session peaks, expressed as a percentage of the limit that would have to be crossed:

```
30%, 4%, 13%, 20%, 13%, 22%, 31%, 23%
```

The highest observation anywhere was 31% of the trigger point. The limit is roughly 3× too high to ever fire.

### Root cause

In `tenths/analyzer.py` (around line 1487):

```python
SPREAD_LIMIT_FRACTION = 0.20
SPREAD_LIMIT_FLOOR_MPH = 6.0
OVER_BRAKING_LIMIT_FRACTION = 0.20      # <-- copied from spread
OVER_BRAKING_LIMIT_FLOOR_MPH = 6.0      # <-- copied from spread
```

Both metrics were given the same 20% fraction, but they measure quantities of very different natural size:

- `min_speed_spread_mph` is the **width of the whole band** of apex speeds across laps (`band_high - band_low`).
- `over_braking_mph` is **one lap versus the centre of the distribution** (`best_lap_min - avg`), computed around line 1615.

A single deviation from a mean is inherently much smaller than the full range of the same data. Reusing the range's threshold for a deviation is the error.

### A second, separate defect in the same feature

`tenths/report.py` contains a **different** over-braking threshold that ignores the computed limit entirely:

- **Line ~1204** (Detailed view table): `overBrk > 8 ? 'bad' : (overBrk > 4 ? 'warn' : '')` — hardcoded 8 and 4 mph, absolute, not speed-relative. This is the exact defect RR-021 fixed elsewhere, still present here.
- **Line ~2400** (`buildCorner()`): `over_braking_limit_mph: zone?.over_braking_limit_mph ?? 8` — falls back to a hardcoded 8 when the computed limit is missing.
- **Line ~2432 and ~2465**: the Summary view correctly compares against `corner.over_braking_limit_mph`.

So the Detailed table colours cells using 8/4 mph while the Summary uses a computed limit. These must not disagree.

### Required work

**Step 1 — measure the real distribution before changing any number.**

Write a temporary script that runs `analyzer.analyze()` over at least 8 archived `.ibt` files from the telemetry archive, and for every corner records `over_braking_mph` together with `avg_apex_mph`. Report:

- the distribution of `over_braking_mph` (min, median, 90th percentile, max);
- the same as a **percentage of `avg_apex_mph`**, which is what the fraction actually controls.

Pick files spanning different cars and track lengths. Use these, which are known to analyze successfully:

```
bmwm2csr_winton national 2026-06-06 22-26-36.ibt
bmwm2g87_summit summit raceway 2026-07-12 18-27-27.ibt
bmwm4evogt4_midohio full 2026-06-03 20-42-11.ibt
bmwm4gt3_limerock 2019 gp 2026-07-18 14-58-07.ibt
bmwm4gt3_roadatlanta full 2026-07-26 15-57-08.ibt
ferrari296gt3_coronado 2026-07-29 22-09-18.ibt
ferrari296gt3_roadamerica full 2026-06-21 16-57-37.ibt
porsche992rgt3_lagunaseca 2026 2026-07-11 16-39-19.ibt
```

Note: some archived files return `None` from `analyze()` because they contain no valid laps (a short Fuji GT4 run and a Charlotte oval run both do). That is expected; skip them.

**Delete the script when you are done with it.**

**Step 2 — OWNER DECISION REQUIRED.** Present your distribution to the owner with these three options and a recommendation. Do not pick one yourself.

- **(a) Retune.** Keep the metric, set the fraction from the measured distribution so it fires on genuinely over-slowed corners. State what percentage of corners would then flag.
- **(b) Redefine.** Compare against something more coachable than the driver's own average — for example the theoretical best lap or a previous PB. Comparing a driver to their own mean may be measuring the wrong thing, since a driver who is consistently over-slowing has a mean that already reflects it and will therefore never flag.
- **(c) Remove.** Drop the diagnosis from user-facing output rather than leaving an inert branch in the UI.

**Step 3 — implement the chosen option.**

If (a) or (b): update the constants in `analyzer.py`, and fix `report.py` so **both** views use `over_braking_limit_mph`. Remove the hardcoded `8` and `4` at line ~1204 and the `?? 8` fallback at line ~2400. If the limit is genuinely absent, the correct behavior is to show no diagnosis, not to invent a threshold.

If (c): remove the diagnosis from `report.py` (the `over_braking` branch in `buildCorner()` at line ~2465, the Summary sentence at ~2432, and the colour classes at ~1204). Keep computing and persisting the field in `analyzer.py` — it is still useful data — but stop presenting it.

**Step 4 — update `docs/COACHING_METRICS_DESIGN.md`** with the decision, the measured distribution, and the sessions used.

### Required tests

Add to `tests/test_min_speed_spread.py`:

- The chosen limit is asserted against the production constants in `analyzer.py`, not a literal copied into the test.
- One case that **does** fire and one that **does not**, using values taken from your measured distribution rather than invented ones.
- If the metric is retained: no hardcoded `8` or `4` remains as an over-braking threshold anywhere in `report.py`. Assert this by searching the generated report/JS text for the old pattern.
- If the metric is removed: assert the generated report contains no over-braking diagnosis text.

### Definition of done

- [ ] Distribution measured and reported, with the session list.
- [ ] Owner has chosen (a), (b), or (c).
- [ ] Chosen option implemented in `analyzer.py` and `report.py`.
- [ ] Only one over-braking threshold exists in the codebase. Confirm with a search for `> 8` and `?? 8` in `report.py`.
- [ ] JavaScript verification procedure from section 1.4 completed, with console output reported.
- [ ] `docs/COACHING_METRICS_DESIGN.md` updated.
- [ ] Full suite passes; new tests included.
- [ ] `docs/RELEASE_REMEDIATION_PLAN.md` RR-022 section gets a Resolution paragraph, and the RR-022 checklist box is ticked.

### Do not

- **Do not touch `min_speed_spread_mph`, `SPREAD_LIMIT_FRACTION`, or `SPREAD_LIMIT_FLOOR_MPH`.** RR-021 validated the spread rule independently at 9 of 41 corners. Re-tuning it as a side effect of this work would undo that.
- Do not tune the limit until one specific session lights up. That is fitting to noise.
- Do not leave the diagnosis in the UI if you cannot make it fire.

---

## RR-011 — Version single-sourcing, artifact tests, and installer validation

**Severity:** High. **Blocked by:** a code-signing certificate, for the signing part only. Everything else here is unblocked.

### Already done, do not redo

- `installer/version_info.txt` exists and supplies the Windows version resource.
- `installer/tenths.spec` references it via `EXE(version=VERSION_FILE)` and raises `SystemExit` with a clear message if the file is missing.
- Verified on the built binary 2026-07-30: ProductName `Tenths`, ProductVersion and FileVersion `0.9.0.0`, CompanyName `Justin Garbiso`, FileDescription `Tenths - iRacing telemetry coaching`.
- `installer\Output\TenthsSetup.exe` compiles: 32.0 MB, correct metadata.

### Remaining work

#### 11a. Version is duplicated across three files with two different formats

| File | Field | Current value | Format |
|---|---|---|---|
| `pyproject.toml` | `version` | `0.9.0` | three-part |
| `tenths/config.py` | `VERSION` | `0.9.0` | three-part |
| `tenths/__init__.py` | `__version__` | `0.9.0` | three-part |
| `installer/version_info.txt` | `filevers`, `prodvers`, `FileVersion`, `ProductVersion` | `0.9.0.0` / `(0, 9, 0, 0)` | **four-part** |
| `installer/tenths_setup.iss` | `MyAppVersion` | `0.9.0` | three-part |

They agree today only because someone edited all five by hand. A release will eventually ship with mismatched versions.

**Important:** a naive string equality test will fail, because `version_info.txt` legitimately uses a four-part Windows version and a tuple form. Your check must normalize: parse the three-part version, append `.0`, and compare against both the tuple and the string fields.

`tests/test_packaging.py` already has a `TestVersionConsistency` class covering `config.py`, `__init__.py`, and `pyproject.toml`. **Extend that existing class**; do not create a second one. Add:

- `installer/version_info.txt` `FileVersion` and `ProductVersion` string fields match `<version>.0`.
- `installer/version_info.txt` `filevers` and `prodvers` tuples match `(major, minor, patch, 0)`.
- `installer/tenths_setup.iss` `MyAppVersion` matches the package version.

Parse the files as text with a regex. Do not import or execute `version_info.txt`; it is not a Python module you should be running.

#### 11b. No test reads the built executable

`tests/test_packaging.py` `TestSpecFileContent` reads the **spec file**, which proves only that the configuration says the right thing. The spec bug fixed on 2026-07-30 is exactly the failure mode this misses: the spec named `version_info.txt` correctly and the build still failed, because the *path* it constructed was wrong.

Add a new test class, for example `TestBuiltArtifact`, that:

- Skips cleanly with a clear reason when `dist/Tenths/Tenths.exe` does not exist. A developer who has not built must not see a failure. Use `pytest.mark.skipif` or `pytest.skip()` with a message telling them to run `python installer/build.py`.
- When the EXE **does** exist, asserts the embedded version resource contains the expected ProductName, ProductVersion, and CompanyName.
- Asserts the bundled resources are present at these exact paths:
  ```
  dist\Tenths\_internal\data\trackLandmarksData.json
  dist\Tenths\_internal\tracks
  dist\Tenths\_internal\assets\tenths.ico
  ```

To read the version resource from Python on Windows without adding a dependency, use `ctypes` with `version.dll` (`GetFileVersionInfoW` / `VerQueryValueW`). If that proves unreliable, shelling out to PowerShell's `(Get-Item $exe).VersionInfo` is acceptable — but then the test must skip gracefully if PowerShell is unavailable rather than failing.

This test being skippable is deliberate. It is a guard against a broken release artifact, not a reason to require a 90 MB build before running unit tests.

#### 11c. Installer has never been install-tested

`TenthsSetup.exe` compiles but has never been installed. Run this matrix and record the result of each step. Ideally on a clean Windows account or VM; if that is not available, say so explicitly in your report rather than implying it was clean.

1. Clean install with "Start Tenths with Windows" checked.
2. Confirm the tray icon appears and the app stays running.
3. Confirm `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Tenths` was created and contains the quoted exe path.
4. Run `"%LOCALAPPDATA%\Tenths\Tenths.exe" config` from a Command Prompt and confirm it prints paths. (This works as of 2026-07-30; the exe forwards arguments to the CLI.)
5. Upgrade install over the top of the existing one. Confirm nothing is lost and no duplicate startup entry appears.
6. Uninstall. Record exactly what is deleted and what remains — this feeds RR-018.
7. Confirm reports under `Documents\iRacing\telemetry` survive uninstall.

#### 11d. Signing — OWNER ACTION, NOT YOURS

Signing needs a real code-signing certificate. **Never fabricate, generate, or commit a signing credential.** Add the signing step to the build as documentation or a clearly-guarded optional step, and leave RR-011 open until the owner supplies a certificate. `Get-AuthenticodeSignature` currently reports `NotSigned`, which is the expected state.

### Definition of done

- [ ] `TestVersionConsistency` covers all five version locations with format-aware comparison.
- [ ] A deliberate version mismatch in any one file makes the suite fail. **Test this by temporarily editing a version, running the suite, confirming failure, then reverting.** Report that you did this.
- [ ] `TestBuiltArtifact` reads the real EXE, and skips with a helpful message when it is absent.
- [ ] Install matrix run and each step's result recorded.
- [ ] Signing documented as blocked, not faked.
- [ ] Full suite passes.

### Do not

- Do not delete the `SystemExit` guard in `tenths.spec`. It exists because the build previously failed with a confusing `FileNotFoundError` from deep inside PyInstaller.
- Do not "fix" a version mismatch by removing one of the locations without checking what reads it.

---

## RR-019 — Explain the 90.5 MB bundle

**Severity:** Low. **Blocked by:** nothing. Mostly measurement and documentation.

### The original hypothesis was wrong — corrected facts

The 2026-07-28 review suspected pytest and setuptools were being collected and inflating the bundle. Measured on 2026-07-30 against the current build, that is **mostly false**:

- `pytest` and `_pytest` do **not** ship. `dist\Tenths\_internal\pytest` does not exist.
- The ~150 `pytest` matches in `build\Tenths\Analysis-00.toc` come mainly from **`numpy._pytesttester`**, which is a numpy module that references pytest. It appears in the dependency graph without pytest itself being bundled.
- `setuptools` **does** ship, but it is **8 files totalling under 0.1 MB**. Removing it would save nothing measurable.
- `jinja2` has **0 occurrences** in the current TOC. The optional-hidden-import warning noted in the original review is **not reproducible** in this build. Do not chase it.

### Where the size actually is — measured

Directories under `dist\Tenths\_internal\`:

| Item | Size | Needed? |
|---|---|---|
| `numpy.libs` | 20.0 MB | Yes — BLAS/LAPACK binaries backing numpy |
| `pandas` | 12.9 MB | Yes — `analyzer.py` uses DataFrames throughout |
| `PIL` | 12.7 MB | Yes — `tray.py` imports `Image` and `ImageDraw` for the tray icon |
| `numpy` | 5.9 MB | Yes |
| `data` | 1.0 MB | Yes — bundled track landmarks |
| `tzdata` | 0.5 MB | Investigate — pulled in by pandas |
| `pandas.libs` | 0.5 MB | Yes |

Top-level files:

| File | Size | Note |
|---|---|---|
| `python314.dll` | 6.5 MB | Required |
| `libcrypto-3.dll` | 5.0 MB | Investigate — trace what needs OpenSSL |
| `sqlite3.dll` | 1.5 MB | Investigate — likely stdlib `sqlite3`, probably unused |
| `base_library.zip` | 1.3 MB | Required |
| `libssl-3.dll` | 0.8 MB | Investigate with libcrypto |

So roughly 58 MB of 90.5 MB is numpy + pandas + PIL, all genuinely used. **The bundle is largely irreducible without dropping pandas**, which would be a major rewrite of `analyzer.py` and is not worth it.

### Required work

1. **Document the composition above** in a packaging section of `docs/TECH_DEBT.md` or a new `docs/PACKAGING.md`, so this is never re-investigated from scratch.
2. **Trace the four "Investigate" items.** Use `build\Tenths\xref-tenths.html` (2.6 MB), which PyInstaller generates as a dependency cross-reference, to find what imports each. Only exclude a module after you can name what imported it and confirm nothing needs it.
3. **If you exclude anything, rebuild and smoke-test.** Add the exclusion to the `excludes` list in `installer/tenths.spec`, rebuild, then launch `dist\Tenths\Tenths.exe`, confirm the tray icon appears, and run `Tenths.exe config`. An exclusion that breaks the frozen app at runtime will not be caught by the test suite, because the suite runs from source.
4. **Measure idle and processing resource use.** The product targets a constrained sim-racing PC, so any user-facing resource claim needs a number behind it. Record idle tray RAM and CPU, and peak RAM and wall time while processing one session. Use Task Manager or `Get-Process Tenths`.
5. **Preserve the evidence files.** `build\Tenths\Analysis-00.toc` (399 KB), `xref-tenths.html` (2.6 MB), and `warn-tenths.txt` (49 KB, 318 lines) are the audit trail. Note that `python installer/build.py` **deletes and recreates `build/` and `dist/` on every run**, so copy anything you want to keep before rebuilding.

### Definition of done

- [ ] Bundle composition documented with measured sizes.
- [ ] Each "Investigate" item resolved: either excluded with the import chain named, or kept with the reason stated.
- [ ] If anything was excluded: rebuilt, tray launched, `config` command works.
- [ ] Idle and processing RAM/CPU measured and recorded.
- [ ] The corrected pytest/setuptools/jinja2 findings replace the old hypothesis in `docs/RELEASE_REMEDIATION_PLAN.md` RR-019 so nobody repeats that investigation.
- [ ] Full suite passes.

### Do not

- Do not remove `pandas`, `numpy`, or `PIL`. All three are used in production code paths.
- Do not add excludes speculatively. An exclusion that breaks the frozen app is invisible to the test suite.
- Do not claim a resource figure you did not measure.

---

## RR-018 — Uninstall and data-retention policy

**Severity:** Medium. **Blocked by:** OWNER DECISION on what should be retained.

### Current state, exactly as configured

`installer/tenths_setup.iss`:

```
line 27:  DefaultDirName={localappdata}\{#MyAppName}          -> C:\Users\<user>\AppData\Local\Tenths
line 63:  [UninstallRun]
line 64:  Filename: "taskkill"; Parameters: "/IM Tenths.exe /F"; Flags: runhidden
line 66:  [UninstallDelete]
line 67:  Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\logs"
line 68:  Type: filesandordirs; Name: "{localappdata}\{#MyAppName}\config"
```

### Three confirmed problems

**1. The `config` directory does not exist and never did.** Settings are written to `{localappdata}\Tenths\settings.json` — a **file**, not a folder. Confirmed in `tenths/config.py` `_settings_path()`, which returns `os.path.join(base, "Tenths", "settings.json")`.

So uninstall deletes a path that was never created, and **leaves the user's actual configuration behind**. Whichever way the policy goes, the current entry achieves nothing.

**2. Application data lives inside the install directory.** Because `DefaultDirName` is `{localappdata}\Tenths` and `APP_DATA_DIR` is also `{localappdata}\Tenths`, the logs, settings, and the program files all share one folder. Uninstall removes the program files from `{app}`, which is the same directory the user's settings sit in. This works today but is fragile, and it makes "delete the app but keep the settings" hard to express.

**3. Inno Setup emits a warning on every compile:**

> `Warning: There are [UninstallRun] section entries without a RunOnceId parameter.`

The `taskkill /IM Tenths.exe /F` entry has no `RunOnceId`, so it may run more than once during uninstallation.

### What is currently retained, for the record

- **Deleted on uninstall:** program files in `{app}`, the `logs` folder, the HKCU `Run` value (via `uninsdeletevalue`).
- **Retained:** `settings.json`; everything under `Documents\iRacing\telemetry` — all reports, notes, summaries, and archived `.ibt` files.

Retaining telemetry and reports is almost certainly correct, since that is the user's data and can be large. But right now it is accidental rather than a stated policy.

### OWNER DECISION REQUIRED

Ask the owner, and do not proceed until answered:

1. **Should `settings.json` survive uninstall?** Retaining it is defensible — a reinstall keeps a custom telemetry root. Deleting it is the cleaner "leave no trace" behavior.
2. **Should the force-kill stay?** `taskkill /F` terminates the tray without letting it shut down cleanly. The watcher's `stop()` exists and does an orderly shutdown. A graceful attempt with `taskkill /F` as a bounded fallback is safer, but adds installer complexity. There is a real risk today: killing mid-processing can leave a partially written report, though the `.ibt` is retained so nothing is permanently lost.
3. **Confirm reports and archived telemetry are never deleted.** Recommend yes. This should be stated in the installer UI, not left implicit.

### Required work once decided

1. Fix the `[UninstallDelete]` entries so they name paths that actually exist and match the decided policy.
2. Add `RunOnceId` to the `[UninstallRun]` entry to clear the compile warning.
3. If graceful shutdown is chosen, implement it and keep `taskkill` as a fallback with a timeout.
4. State the retention policy in user-visible text: the installer's finish page or an uninstall confirmation message, plus `docs/GETTING_STARTED.md` and `docs/BETA_TESTING.md`. Note that `BETA_TESTING.md` already says "removes the app and its logs" and "your reports and archived telemetry are left in place" — verify that stays true and add the settings decision.
5. Consider separating application data from the install directory (for example `{localappdata}\Tenths` for the app and `{localappdata}\TenthsData` for logs and settings). **This is a behavior change that would orphan existing users' settings, so raise it with the owner rather than doing it unilaterally.**

### Required tests

Installer behavior cannot be unit-tested meaningfully, so:

- Add a test to `tests/test_packaging.py` asserting that every path named in `[UninstallDelete]` corresponds to a path the application actually creates. Derive the expected paths from `tenths/config.py` (`LOG_DIR`, `SETTINGS_PATH`, `APP_DATA_DIR`) rather than hardcoding strings, so the test catches future drift. This is the test that would have caught the phantom `config` directory.
- Record the manual uninstall verification from RR-011 step 6.

### Definition of done

- [ ] Owner has answered all three decisions, and the answers are written into `docs/RELEASE_REMEDIATION_PLAN.md` RR-018.
- [ ] `[UninstallDelete]` names only real paths and matches the policy.
- [ ] Inno Setup compiles with **no** `RunOnceId` warning.
- [ ] Retention policy stated in user-facing documentation.
- [ ] Packaging test ties uninstall paths to `config.py`.
- [ ] Installer rebuilt and uninstall manually verified.
- [ ] Full suite passes.

### Do not

- Do not delete user telemetry, reports, or archived `.ibt` files under any policy. That is unrecoverable data the user may have spent months accumulating.
- Do not change `DefaultDirName` without discussing the upgrade path for existing installs.

---

## RR-009 — The Detailed report is not offline

**Severity:** High. **Blocked by:** OWNER DECISION between Option A and Option B.

### Exact current state

`tenths/report.py` contains six remote references. Verified 2026-07-30:

| Line | Reference |
|---|---|
| 229 | `<link rel="preconnect" href="https://fonts.googleapis.com">` |
| 230 | `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>` |
| 231 | Google Fonts CSS — Orbitron, Inter, JetBrains Mono |
| 232 | `https://unpkg.com/leaflet@1.9.4/dist/leaflet.css` |
| 391 | `https://unpkg.com/leaflet@1.9.4/dist/leaflet.js` |
| 392 | `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js` |

### Three properties that are easy to conflate

Be precise about these; the original review erred by treating them as one thing.

1. **Single local file** — the report is one `.html` on disk. **True today.**
2. **No server or runtime API** — nothing needs to be running to view it. **True today.**
3. **No outbound network requests** — opening it contacts nobody. **False today** for the Detailed view.

The **Summary** view is entirely locally implemented and satisfies the offline requirement. Only the **Detailed** view's map, charts, and fonts are remote. `README.md` line 7 already describes this accurately — do not "fix" that line into a promise the code does not keep.

### OWNER DECISION REQUIRED

- **Option A — make the report fully offline.** Bundle pinned Leaflet 1.9.4 and Chart.js 4.4.0, and remove the remote font requests. Preferred if the product should promise offline operation.
- **Option B — keep the CDNs.** Narrow every offline claim to the Summary view and disclose that opening Detailed contacts third parties. Cheaper, and already partly documented.

If Option A, a **second decision** is needed: inline the assets into the HTML to keep a literally self-contained single file (larger reports, roughly +250 KB each), or ship them as sibling local files (smaller reports, but the report is no longer one portable file). Ask which matters more — portability of a single file, or report size.

### Required work for Option A

1. Vendor Leaflet 1.9.4 (CSS + JS) and Chart.js 4.4.0 into the repo, for example under `tenths/assets/vendor/`. Pin exact versions; do not fetch "latest".
2. Add those files to the `datas` list in `installer/tenths.spec` so the frozen build includes them, and confirm they land under `dist\Tenths\_internal\`.
3. Replace the fonts. Either bundle webfonts with verified redistribution terms, or use a local font stack. **Check the Pit Wall theme requirements in `docs/HTML_REPORT_DESIGN.md` first** — Orbitron for hero numbers, JetBrains Mono for data, Inter for labels are mandated there. If you substitute fallbacks, the visual theme changes, which needs owner sign-off.
4. Both Leaflet and Chart.js licenses must be recorded in the RR-001 notices file. Chart.js and Leaflet are both permissive, but **record the actual license text from the version you vendor** rather than asserting from memory.
5. Resolve resource paths for both source and frozen modes. `tenths/config.py` `_find_package_root()` already handles `sys._MEIPASS`; reuse it rather than writing new path logic.

### Required verification

- Disable networking, open a generated report, and check **both** tabs.
- Open DevTools → Network tab, reload, and confirm **zero external requests**. This is the actual acceptance test; a report that renders offline because the browser cached the CDN asset is still broken.
- Follow the section 1.4 JavaScript procedure.
- Confirm the map renders and is interactive, charts render, and tab switching works.
- Test from the **frozen build**, not only from source, since asset paths differ.

### Required tests

- Assert the generated HTML contains no `https://` reference. This is a simple, strong test: search the report string for `http://` and `https://` and assert none are present in asset positions.
- Assert the vendored asset files exist in the repo.
- Assert `installer/tenths.spec` lists them in `datas`.
- For Option B instead: assert the Summary view has no remote dependency, and that documentation discloses the Detailed view's CDN use.

### Definition of done

- [ ] Owner has chosen A or B, and the sub-decision if A.
- [ ] Implementation matches the choice.
- [ ] Every user-facing claim in `README.md`, `docs/GETTING_STARTED.md`, and `docs/BETA_TESTING.md` agrees with the artifact. `BETA_TESTING.md` currently has a "Reports need internet on the Detailed tab" section — remove it under Option A, keep it under Option B.
- [ ] DevTools Network tab shows zero external requests (Option A).
- [ ] Verified from the frozen build.
- [ ] Asset licenses recorded for RR-001.
- [ ] Full suite passes.

### Do not

- Do not fetch assets at report-generation time as a workaround. That moves the network dependency rather than removing it, and fails on a machine that was offline when the session was processed.
- Do not upgrade Leaflet or Chart.js versions while doing this. Vendor the versions currently referenced so any visual change is attributable to bundling, not to a version bump.

---

## RR-006 — Manual processing must produce one complete artifact set per session

**Severity:** Release blocker. **Blocked by:** nothing. **This is the largest task in this document.** Read all of it before editing.

### Why this matters

The owner's rule, from the project standards: *every telemetry session gets its own report; never overwrite because another session was faster.* The watcher already honours this. Manual `tenths process` does not — it groups sessions by day, picks one "best" session, and writes a single report for the whole day. Drive three races in an evening and you get one report for the fastest, with the other two silently discarded.

### Exact current behavior in `tenths/process.py`

All line numbers are approximate and will drift; find the code by the quoted text.

**1. Files are grouped by day (line ~605):**

```python
key = (file_info['car'], file_info['track'], file_info['date'])
```

The session **time** is deliberately excluded from the key. This is the root of the whole issue.

**2. Output goes to a date-level directory (line ~690):**

```python
session_dir = os.path.join(TELEMETRY_ROOT, car, track, date)
```

Compare with the watcher, `tenths/service/watcher.py` line ~576, which is correct:

```python
session_dir = os.path.join(TELEMETRY_ROOT, car, track, date, file_info['time'])
```

**3. One session is chosen to represent the day (line ~705):**

```python
def session_priority(s):
    ...  # Race > Qualify > Practice, then fastest lap
best_session = max(sessions, key=session_priority)
```

The report and the JSON summary are generated for `best_session` only. The other sessions of that day contribute to combined notes and are otherwise dropped.

**4. Notes are combined for the day, not per session (line ~693):**

```python
notes_content = generate_day_notes(sessions, car, track, date, track_map, baseline)
```

**5. The `.ibt` is archived immediately after analysis, before any output exists (line ~657):**

```python
sessions.append((file_info, data, race_result))

# Archive the .ibt
if not dry_run:
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    shutil.move(filepath, os.path.join(ARCHIVE_DIR, os.path.basename(filepath)))
```

If report generation then fails, the source has already been moved and the session produced nothing. **This part is RR-007, not RR-006** — but you will be editing the same loop, so read RR-007 before you start and consider doing both together.

### The canonical contract you are implementing

```text
<telemetry-root>\<car>\<track>\<YYYY-MM-DD>\<HH-MM-SS>\
    session_report.html
    session_notes.md
    session_summary.json
```

Rules:

- Watcher, manual `process`, standalone `report`, and standalone `summary` must all use **one shared path builder**.
- Watcher and manual `process` must produce **all three** artifacts for every successfully processed session.
- Standalone `report` and `summary` keep their single-artifact behavior, but write into the same canonical per-session directory. **Do not change them to emit all three** — that would be a product change, and it is not approved.
- Never pick one representative session. A daily aggregate may exist as an *extra* artifact but must never replace per-session output.
- If a target directory already exists for a *different* source file, create a deterministic collision-safe suffix. Never overwrite.
- Processing commands archive the `.ibt` only after all required artifacts are written. Standalone generation commands do not archive at all.

### Implementation, in stages

**Stage A — the shared path builder. Do this first and get it merged before Stage B.**

1. Create one function, for example `session_output_dir(telemetry_root, car, track, date, time)`, in a sensible shared location. `tenths/config.py` is a reasonable home; do not put it in `process.py`, because `watcher.py` importing from `process.py` is already a tangle.
2. Give it deterministic collision handling. Decide the suffix scheme (for example `-2`, `-3`) and document it in the docstring.
3. Move `REQUIRED_ARTIFACTS` (currently `watcher.py` line ~45) next to it so both callers share one definition.
4. Change `watcher.py` line ~576 to call it. Behavior must not change — the watcher is already correct, so its tests must still pass untouched. **If a watcher test fails at this point, your helper is wrong.** That is the signal Stage A is designed to give you.
5. Also fix the known inconsistency recorded in the RR-004 resolution: `TelemetryWatcher.__init__` accepts a `telemetry_root` argument and stores it as `self._root`, but `_run_pipeline` writes output using the **global** `config.TELEMETRY_ROOT` imported from `process.py` (line ~520). These differ whenever the argument is used, which today is only in tests. Make `_run_pipeline` use `self._root`.

**Stage B — make manual processing per-session.**

1. Change the grouping key at line ~605 to include `file_info['time']`, or drop the grouping entirely and iterate files directly. Grouping only still matters if a daily aggregate is retained.
2. For **each** session, write all three artifacts to its own time-level directory via the Stage A helper.
3. Delete the `session_priority` / `best_session` selection. Every session gets a report.
4. Decide what happens to `generate_day_notes()`. Two acceptable outcomes: per-session notes replace it entirely, or per-session notes are written *and* a day-level aggregate is additionally written to the date folder. **Do not** let the aggregate be the only notes output. If you keep the aggregate, keep it out of the time folders so the index does not treat it as a session.
5. Keep race-result matching per source session (`find_race_result` in the loop) — do not match once for the day.
6. Regenerate the master index after the batch, and confirm no session is hidden. `tenths/index_generator.py` walks the output tree; check it handles the additional folders correctly and does not list a day-level aggregate as if it were a session.
7. Move archiving to after all artifacts are confirmed written. Mirror the watcher, which checks `REQUIRED_ARTIFACTS` exist before calling archive. That is RR-007's requirement and the code is already written there — reuse the pattern.

### Required tests

Add to a new `tests/test_process_per_session.py`, or extend existing process tests:

- Two same-day `.ibt` files processed by `process` create **two** time folders, each with all three artifacts.
- The **slower** of two same-day sessions still gets its own report. This is the regression that matters most; assert the report file exists and is non-empty.
- Manual and watcher path generation return **identical** paths for the same filename metadata. Call both production code paths and compare, rather than asserting a hardcoded string.
- A pre-existing directory for a different source file is not overwritten; the collision suffix is applied and both sets of artifacts survive.
- Standalone `report` writes only `session_report.html` into the canonical time folder, and does **not** create notes or summary, and does **not** archive the input.
- Standalone `summary` behaves equivalently for `session_summary.json`.
- The `.ibt` is not archived when artifact writing fails.

Use `tests/synthetic_ibt.py` to build inputs. It writes a byte-valid `.ibt` that pyirsdk opens, with exact known lap times, so you can assert precise values instead of ranges. Two synthetic sessions with different times on the same date is exactly the fixture this task needs. Read `tests/test_pipeline_synthetic.py` for usage examples.

### Definition of done

- [ ] One shared path builder; `watcher.py`, `process.py`, and both standalone CLI commands all call it.
- [ ] `_run_pipeline` uses `self._root`, not the global.
- [ ] No representative-session selection remains anywhere.
- [ ] Every session processed by `process` has its own report, notes, and summary.
- [ ] Standalone commands still write exactly one artifact each and never archive.
- [ ] Collision handling is deterministic and tested.
- [ ] Master index shows every session.
- [ ] All existing watcher tests pass **without modification**.
- [ ] Full suite passes with new tests added.
- [ ] `README.md` line ~98 and `docs/GETTING_STARTED.md` line ~107 caveats about manual CLI output are now removed, since they become false. **This is the RR-017 follow-up for this task — do not forget it.**
- [ ] `docs/RELEASE_REMEDIATION_PLAN.md` RR-006 gets a Resolution paragraph and its checklist box ticked.

### Do not

- Do not change standalone `report` or `summary` to emit all three artifacts. Not approved.
- Do not delete a day-level artifact that already exists in the owner's real telemetry. You are not permitted to write there at all.
- Do not "solve" collisions by overwriting or by using a timestamp of the current clock. It must be deterministic so re-running produces the same layout.

---

## RR-007 — Isolate manual failures and archive transactionally

**Severity:** High. **Blocked by:** RR-006. **Deferred by the owner** for the beta, because beta testers use the tray watcher and never run `tenths process`.

This is deferred, not dismissed. The defect is real for the owner, who does run manual processing. Do not mark it resolved by arguing testers are unaffected.

### The two defects

**1. Archiving happens before output exists.** Covered in RR-006 item 5 above, `process.py` line ~657. The source `.ibt` is moved to `_archive` right after analysis. Every output failure after that point loses the session.

**2. No per-file failure isolation.** An exception while analyzing or writing one file propagates out of the loop and aborts the whole batch. Process 20 files, hit a corrupt one at position 3, lose 17.

### Required work

1. Wrap per-file analysis and output in a try/except that logs and continues to the next file.
2. Print a batch summary at the end: counts of succeeded, skipped, and failed, with filenames and an actionable reason for each failure.
3. Archive only after all required artifacts for **that** file are confirmed written. Reuse the `REQUIRED_ARTIFACTS` existence check from `watcher.py`.
4. Leave failed sources in place so they can be retried.
5. Handle a missing telemetry root cleanly: print actionable setup guidance and exit without a traceback. `tenths/config.py` and the `tenths config` command already do this well — reuse their messaging rather than writing new text.
6. Treat a malformed race-result file as non-fatal to telemetry analysis. `tenths/results.py` already returns `None` rather than raising after the RR-010 fix, so verify this rather than re-implementing it.

### Required tests

- A corrupt first file does not prevent a valid second file from being processed.
- An output failure leaves the source unarchived. Force this by patching the report writer to raise.
- A successful file is archived exactly once.
- A missing telemetry root exits cleanly with a non-zero status and no traceback.
- The batch summary counts and filenames are accurate.

### Definition of done

- [ ] No single corrupt input aborts the batch.
- [ ] No source archived before its artifacts exist.
- [ ] Batch summary is accurate and actionable.
- [ ] Full suite passes with new tests.
- [ ] `docs/RELEASE_REMEDIATION_PLAN.md` RR-007 updated from Deferred to Resolved, with a Resolution paragraph.

### Do not

- Do not swallow exceptions silently. Every caught failure must be logged with the filename and the stage it failed at.
- Do not retry inside `process`. Retry is the watcher's job; manual processing should report and move on.

---

## RR-001 — Landmark dataset provenance and third-party notices

**Severity:** Release gate. **Blocked by:** the owner and, if terms are ambiguous, legal advice.

### Read this before doing anything

**You must not conclude what license applies to this dataset.** An AI model asserting a license from memory or from a repository badge is how this issue was created in the first place. Your job is to gather verifiable facts and produce a notices file with the *dependency* licenses you can verify. The dataset conclusion belongs to the owner.

### Current state

- Bundled file: `tenths/data/trackLandmarksData.json`, **1.0 MB**, ships in the frozen app at `dist\Tenths\_internal\data\trackLandmarksData.json`.
- It is the **primary** track data source, covering roughly 450 tracks. `tenths/track_map.py` reads it; the `tracks/*.md` files are a fallback.
- `LICENSE` covers Tenths only (MIT).
- `THIRD_PARTY_NOTICES.md` **does not exist**.
- `docs/TECH_DEBT.md` line ~91 already correctly states the former GPL-3.0 assumption is not evidence. Do not reintroduce that claim.
- The dataset is understood to originate from CrewChief. The archived CrewChief GitHub repository presents itself as MIT and redirects development to GitLab. **A repository-level badge is not dataset-specific evidence**, and the redirect means the current terms may live elsewhere.

### What you can and should do

1. **Record reproducible provenance.** Find and document: exact source URL, repository revision or commit hash, retrieval date, dataset owner, and whether Tenths modified the file. If you cannot establish any of these, say which ones and stop.
2. **Draft `THIRD_PARTY_NOTICES.md`** at the repo root covering every dependency shipped in the frozen application. These are verifiable from the installed packages and their bundled license files, so this part is safe work. From `pyproject.toml`, the runtime dependencies are:
   ```
   pyirsdk>=1.3,<2.0
   pandas>=2.0,<3.0
   numpy>=1.24,<3.0
   watchdog>=3.0,<5.0
   winotify>=1.1,<2.0
   pystray>=0.19,<1.0
   Pillow>=10.0,<12.0
   PyYAML>=6.0,<7.0
   ```
   Also include anything vendored for RR-009 if that lands first (Leaflet, Chart.js, any webfont). Copy the **actual license text from the installed package**, typically in its `dist-info` directory; do not write license text from memory.
3. **Leave the dataset section as an explicit open question** in that file, phrased as unresolved, until the owner confirms.
4. **Add the notices file to the frozen bundle.** Add it to `datas` in `installer/tenths.spec` and verify it appears in `dist\Tenths\`.
5. **Do not correct provenance statements in the docs to a new conclusion.** Only remove unsupported assertions and point to the notices file.

### The fallback, if rights cannot be established

Remove `trackLandmarksData.json` from the distributed artifacts and rely on the `tracks/*.md` fallback. Note the consequence honestly: coverage drops from ~450 tracks to the handful with hand-authored maps, which is a serious product regression. That trade-off is the owner's call. If it comes to this, `tenths/track_map.py` must degrade gracefully with the dataset absent — write a test that asserts this, since it would otherwise be discovered by a user.

### Required tests

- `THIRD_PARTY_NOTICES.md` exists at the repo root.
- `installer/tenths.spec` includes it in `datas`.
- `tenths/track_map.py` behaves sanely when `trackLandmarksData.json` is absent (falls back, does not raise). This is worth having regardless of the licensing outcome.

### Definition of done

- [ ] Provenance facts recorded, or the specific unknowns documented.
- [ ] `THIRD_PARTY_NOTICES.md` covers every shipped dependency with real license text.
- [ ] Notices file present in source and in `dist\Tenths\`.
- [ ] No document asserts a dataset license that has not been verified.
- [ ] Owner has confirmed the dataset position, or the issue remains explicitly open.
- [ ] Full suite passes.

### Do not

- Do not state or imply a license conclusion for the landmark dataset.
- Do not remove the dataset without the owner's decision — it is the primary track source.
- Do not paraphrase license text. Reproduce it verbatim from the package.

---

## 3. How to report your work

For each issue you complete, report in this shape. Keep it factual.

```
RR-0XX — <title>

What I changed
  <file>:<function> — <what and why, one line each>

What I verified
  Suite: <N> passed, <N> failed, <N> skipped
  <any manual verification: browser console, frozen build, install test>
  <the specific assertion that proves the defect is gone>

What I could not verify
  <be explicit; do not imply you checked something you did not>

Decisions I need
  <anything marked OWNER DECISION REQUIRED that is still unanswered>

New issues found
  <if you found a new defect, propose RR-023 etc. rather than folding it into an
   unrelated issue>
```

### Rules for reporting

- **State test counts as numbers**, not "all tests pass".
- **Distinguish verified from assumed.** If you did not run the frozen build, say so.
- **If you found a new defect, give it a new ID.** Do not hide it inside an unrelated issue. Add it to `docs/RELEASE_REMEDIATION_PLAN.md` with the same structure as the existing entries: evidence, root cause, required work, required tests, acceptance criteria.
- **If you changed a test, say which and why.** An unexplained test change is treated as a weakened test.

---

## 4. Updating the plan document

`docs/RELEASE_REMEDIATION_PLAN.md` is the canonical record. When you finish an issue:

1. Update its row in the severity table (section 3) with `~~strikethrough~~` and **RESOLVED &lt;date&gt;**.
2. Add a `**Resolution (<date>).**` paragraph under that issue's specification, naming: the files changed, the tests added, anything you deliberately did differently from the spec and why, and what you verified.
3. Tick its box in the release gate checklist (section 7), with a one-line summary after the text.
4. Update the **Last updated** line at the top of the file with the new resolved count and the current suite total.
5. Keep issue IDs stable. Never renumber.

Section 9 of that document is the formal protocol. Follow it.

---

## 5. Release gate reminder

A green test suite is **not** release readiness. Public distribution still requires all of the following, none of which the suite can tell you:

- Legal provenance for the landmark dataset (RR-001).
- A valid code signature (RR-011).
- Offline behavior matching the documented claims (RR-009).
- Clean-machine install, upgrade, and uninstall testing (RR-011, RR-018).
- Documentation that matches the shipped application (RR-017).
- Measured resource use behind any performance claim (RR-019).

Current status: **NO-GO for public distribution.** Adequate for beta testers who have been told it is a beta, which is what `docs/BETA_TESTING.md` is for.
