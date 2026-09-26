# AGENTS.md — orientation for AI agents working on Tenths

This repository is maintained by AI agents (Claude, Kiro, …) for a single owner.
Read this file first. It points at the one authoritative place for each rule
rather than restating it; if this file and the code disagree, the code and its
tests win — fix this file.

## What Tenths is

A Windows tray app for iRacing drivers. It watches for new `.ibt` telemetry,
analyses each session, and writes an offline HTML coaching report, markdown
notes, a `session_summary.json`, and an entry in the **setup notebook** (a per
car/track setup history an AI race engineer reads). Python 3.14, pyirsdk,
pandas, numpy. No accounts, no network at runtime — keep it that way; any
online integration must be optional and off by default.

## Read in this order

1. `README.md` — features, CLI, project layout, config.
2. `docs/POST_MVP.md` — deferred work and *why* each item was deferred.
3. `docs/RELEASE_REMEDIATION_PLAN.md` — issue history and the release gate.
4. `docs/TECH_DEBT.md` — known defects; resolved items keep their record.
5. Live work queues: `docs/CORNER_DATA_NEXT_STEPS.md` (turn data).
6. `docs/RELATED_TOOLS_RESEARCH.md` — competing and open-source tools, their
   licenses (what may and may not be reused), and ideas already adopted. Check
   it before researching the landscape again.
7. `CHANGELOG.md` `[Unreleased]` — what has changed since the last beta.

Documents with a **HISTORICAL** banner at the top (`OUTSTANDING_ISSUES.md`,
`DISTRIBUTION_READINESS.md`, `HANDOFF.md`) are context, not instructions.

## Commands

```cmd
python -m pip install -e .
python -m pytest tests/ -q            # the executable spec; must stay green
python -m tenths.cli config           # resolved paths and settings
python -m tenths.cli process <file>   # full pipeline for one .ibt
python -m tenths.cli notebook         # setup notebooks; `notebook rebuild [car]`
```

CI (`.github/workflows/ci.yml`) runs the suite on push. Releases: see
`docs/RELEASING.md` — `release.py` refuses unpushed commits.

## Contracts and where each one lives

| Topic | Authoritative location |
|---|---|
| Units: store SI, convert once at a display boundary | `tenths/units.py` module docstring |
| Lap times (iRacing publishes `LapLastLapTime` ~1-2 s after the line) | `analyzer.lap_times`; TECH_DEBT A5 |
| Tyre edge orientation (L/M/R channels; left edge = outer on LF/LR) | `tenths/tyres.py` |
| `session_summary.json` schema (always mph — machine contract) | `tenths/summary.py` |
| Setup notebook: sources of every value, balance metric, warm-up rule, noise floor | `tenths/setup_notebook.py` module docstring |
| Race-engineer agent instructions (generated into the notebook folder) | `ENGINEER_GUIDE` in `tenths/setup_notebook.py` |
| Trail-braking diagnosis thresholds and their provenance | comment above `analyzer.diagnose_trail_zone` |
| Turn names / landmark data and its known unreliability | `tenths/track_map.py`; `docs/CORNER_DATA_NEXT_STEPS.md` |

## iRacing data facts that have caused real bugs

Each was measured on real sessions; the linked location has the evidence.

- `LapLastLapTime` lags the lap counter, so reading it at a lap's end gives the
  previous lap's time. Use `analyzer.lap_times`. (TECH_DEBT A5)
- Tyre `…tempL/M/R`, `…wearL/M/R`, `…tempCL/CM/CR` are edges seen from behind
  the car: on left-side tyres the left edge is the outer one. Use
  `tenths.tyres.inner_middle_outer`.
- The `CarSetup` YAML in an `.ibt` is **always metric**, whatever units the
  garage displays. Its in-car section (brake bias, TC, ABS) can differ from
  what was driven — use the live `dc*` channels. A setup's *name* is not proof
  of its contents; the garage's File Actions > Export writes a readable `.htm`.
- Carcass temperatures and tyre wear only update when the car enters the pits.
- Early laps of a stint are tyre warm-up; pressures rise 2-4 %/lap until they
  settle. Balance comparisons use settled laps only.
- The iRacing API has no per-corner positions; do not re-investigate
  (`docs/IRACING_TRACK_API_INVESTIGATION.md`). `.sto` setup files are encrypted;
  do not try to read or write them.

## Tests

- Tests are the statement of behaviour. Encode an invariant as a test, not a
  comment. Every bug fix gets a regression test that fails on the old code.
- `tests/synthetic_ibt.py` writes byte-valid `.ibt` files with known ground
  truth and runs anywhere (including CI). It reproduces iRacing's lap-time lag.
- Integration tests prefer the owner's archive under
  `~/Documents/iRacing/telemetry/_archive` and fall back to anonymised fixtures
  in `tests/data` (`tests/test_fixture_privacy.py` guards the anonymisation).
- `tests/conftest.py` autouse guards stop any test writing to the registry, the
  repo's `tracks/`, or the owner's real setup notebook. Add a guard whenever a
  new code path writes outside `tmp_path`.

## How to change things

- One authoritative location per contract. Point at it; don't copy it.
- User-visible change → `CHANGELOG.md` `[Unreleased]`. Defect found or fixed →
  `docs/TECH_DEBT.md` (resolved items keep a short record of cause and
  evidence). Deferred idea → `docs/POST_MVP.md` with the reasoning.
- When a document stops being true, fix it or add a HISTORICAL banner — stale
  instructions are worse than none.
- Commit messages explain *why*, cite the evidence (session, numbers), and name
  what a later agent must not undo. End with the `Co-Authored-By` line your
  harness specifies.
- Work that spans sessions happens in git worktrees under `.claude/worktrees/`
  on `claude/*` branches; rebase onto `main`, run the full suite, then
  fast-forward `main` and push. Delete merged branches and worktrees.
- Never commit the owner's data: telemetry, setup notebooks, `.sto` or export
  files, `settings.json`. These live outside the repo.

## Owner's data (outside the repo)

- Telemetry: `~/Documents/iRacing/telemetry` (processed `.ibt` in `_archive`,
  reports in `<car>/<track>/<date>/<time>/`).
- Setup notebook: `<telemetry>/setup_notebook/` — `ENGINEER.md`, per car
  `car_notes.md` and `limits.json`, per track `.md` / `.json` / `.notes.md`
  (the `.notes.md` experiment logs are the record of what setups were tested and
  why they were kept or reverted).
- Settings and logs: `%LOCALAPPDATA%\Tenths`.
