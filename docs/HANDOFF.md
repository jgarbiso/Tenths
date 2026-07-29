# Tenths Development Handoff — Context for Next Session

> **Historical handoff:** Feature statuses, test counts, landmark integration steps, and prior license assumptions in this document may be stale. Before implementing anything, read [`RELEASE_REMEDIATION_PLAN.md`](RELEASE_REMEDIATION_PLAN.md), which is the canonical 2026-07-28 release plan. Do not infer the landmark dataset license from historical notes, and do not reimplement landmark integration—it is already wired into `track_map.py`.

## Historical State (as of 2026-07-22)

### What Tenths Is
An iRacing telemetry analysis tool that auto-processes .ibt files and generates interactive HTML coaching reports with a VR-readable Summary View. Runs as a Windows system tray app — zero-friction background service.

### Repository
- **Path:** `c:\Users\justi\Documents\Sim\Tenths`
- **GitHub:** `git@github.com:jgarbiso/Tenths.git`
- **Branch:** `main`
- **Version:** 0.9.0
- **Tests:** 176 passing (pytest), ~10s runtime

### Architecture
```
tenths/
├── config.py              # Centralized config (auto-detects paths)
├── cli.py                 # CLI entry: watch, tray, process, report, summary, migrate, index
├── analyzer.py            # Core .ibt parser + all metrics
├── process.py             # Session notes orchestrator
├── report.py              # HTML report generator (Summary + Detailed views, inline JS/CSS)
├── summary.py             # session_summary.json generator + schema migration
├── index_generator.py     # Master session browser (index.html at telemetry root)
├── track_map.py           # Track map file parser (% → turn names)
├── track_map_generator.py # Auto-generates skeleton track maps from GPS
├── results.py             # iRacing race result parser
├── incidents.py           # Incident forensics
├── data/
│   └── trackLandmarksData.json  # Bundled corner data (457 iRacing tracks, from CrewChief community)
└── service/
    ├── watcher.py         # File system watcher (watchdog, event-driven)
    ├── notifier.py        # Windows toast notifications (winotify)
    └── tray.py            # System tray app (pystray)
```

### Key Design Decisions
- **Two-tab report** — Summary (VR-readable, coaching-first) + Detailed (full telemetry)
- **Pit Wall theme** — dark mode with specific color tokens (docs/HTML_REPORT_DESIGN.md)
- **Orbitron font** for hero numbers, Inter for UI, JetBrains Mono for data
- **Unified braking zones table** — one template for ALL car classes
- **Event-driven watcher** — watchdog (ReadDirectoryChangesW), zero CPU when idle
- **BELOW_NORMAL thread priority** during processing when iRacing may be running
- **Toast notification** by default, browser auto-open is opt-in (`--open` flag)
- **No git commit** by default (`--git` flag to opt-in)
- **Config auto-detects** `~/Documents/iRacing/telemetry` for any user
- **Master index auto-regenerates** after each session processed by watcher

### What's Complete
- ✅ CLI Enhancement Tasks 1.1–1.7 (JSON contract, schema migration, track maps, metrics)
- ✅ HTML Report — Detailed View (map, charts, compare, brake release, brake points, steering)
- ✅ HTML Report — Summary View (hero numbers, coaching sentences, focus cards, mini track map, speed context)
- ✅ Watcher Tier 1–3 (CLI watch, toast notifications, system tray app)
- ✅ Coaching metrics (Apex ±, Input Stability, Brake Duration, Corner Ranking, T2Peak, Thr On, Thr Lag, Brake Linearity)
- ✅ Coaching Sentences (plain-English per-corner technique diagnosis in Summary View)
- ✅ Master Session Index (browser with type-ahead filters, auto-regenerates)
- ✅ PyInstaller + Inno Setup packaging
- ✅ Security review + fixes
- ✅ Per-session folders (no overwrite)
- ✅ Track map library (30+ hand-built configs + 457-track bundled database from CrewChief community)
- ✅ CLI path-with-spaces bug fixed (P2)
- ✅ Leaflet hidden-container rendering fix
- ✅ Summary View coaching threshold lowered to 0.1s
- ✅ MVP prep (centralized config, no hardcoded paths, v0.9.0)

---

## Summary View Features (NEW — 2026-06-21)

The report now opens to a **Summary tab** by default:
- **Hero numbers**: Best Lap, Recoverable Time, Delta vs Previous, Laps
- **Next Race Focus**: Single most important coaching priority with turn name + speed context
- **Focus Cards**: Top 3 time-loss corners (excluding Next Race Focus) with coaching sentences
- **Speed context**: Amber "157→70mph" badge on each card for corner identification
- **Mini track map**: Canvas-rendered GPS outline with red dots on problem corners
- **Drill-down**: Click any card to jump to supporting data in Detailed view
- **View persistence**: localStorage remembers your tab preference per report
- **Leaflet fix**: Map invalidates size on first show (hidden container issue resolved)
- **No external deps**: Summary View works fully offline (no CDN needed)

---

## Track Map Library

**Bundled database:** `tenths/data/trackLandmarksData.json` — integrated as the primary turn-name source in `track_map.py`. Its exact source revision and dataset-specific redistribution terms remain unresolved; see RR-001 in `RELEASE_REMEDIATION_PLAN.md`. CrewChief is not required at runtime.

**Hand-built configs** (30+ track map .md files) — used until landmark integration is complete:
- Okayama (Full)
- Oulton Park (8 configs)
- Navarra (Speed Circuit)
- Road America (Full/Bend)
- Road Atlanta (Full)
- VIR (5 configs)
- Summit Point (5 configs)
- Tsukuba (7 configs)
- Laguna Seca
- Lime Rock (5 configs)
- Winton National, Mid-Ohio (Full, Chicane)

**Known slug mismatches** (TM1 bug — will be resolved by landmark integration):
- `summit_summit_raceway` (iRacing) → `summit_point_raceway.md` (our file)
- `limerock_2019_gp` (iRacing) → `lime_rock_grand_prix.md` (our file)

---

## Known Tech Debt (Priority)

| ID | Issue | Status |
|----|-------|--------|
| TM1-4 | Track map system bugs (slug matching, percentage ambiguity) | **Solution found** — bundled trackLandmarksData.json, implementation next session |
| P2 | CLI path with spaces fails | **FIXED** |
| P3 | No standalone race results processing | Documented, high priority future |
| NEW | Min Speed Spread metric | **BUILT (2026-07-28)** — over-slowing detection, corner attribution corrected same night |
| RR-021 | Spread threshold is absolute mph, misfires on fast corners | **OPEN — high** — needs to be speed-relative |
| NEW | Coaching threshold at 0.1s may show noise on some tracks | Monitor — may need per-track or adaptive threshold |

See `docs/TECH_DEBT.md` for full list and implementation plans.

---

## NEXT STEPS (in priority order)

### 1. Release remediation (CURRENT)
**Goal:** Close the public-distribution gates in priority order.
- Follow `docs/RELEASE_REMEDIATION_PLAN.md` as the canonical issue list.
- Do not repeat the already completed landmark integration.
- Resolve RR-001 provenance before distributing the bundled dataset.
- Address correctness and durability blockers before feature enhancements.
- Run the mandatory full test suite after every code change.

### 2. Min Speed Spread coaching metric (✅ BUILT — 2026-07-28)
Detects over-slowing by comparing per-lap min speed to the best lap's min speed.
- Exposes why a driver is slow even when they are "consistent" (low time variance)
- Ranks above brake linearity in the Summary View coaching priority
- Excludes incident laps and rejects single-lap outliers from the band, mean and std
- Apex search window is centred on the located apex, bounded in metres, clamped to neighbours
- See `docs/COACHING_METRICS_DESIGN.md` section 2a for as-built behavior and the audit

### 2a. Corner attribution audit (2026-07-28 — READ BEFORE TOUCHING SPEED METRICS)
The first Min Speed Spread build reported "8.5 mph over-slowing at T6" on the Qualcomm race. The flagged lap was actually the **fastest** through that corner. Root causes, all fixed the same night:
- Apex window was centred on the braking zone; the apex is 55–273m downstream
- Window was `centre-5%/+8%` — ~703m on a 5.4km lap, so it sampled unrelated track
- The band trimmed outliers but the mean did not, so a rejected value still skewed the result
- 4 of 8 corner sectors overlapped, double-counting summed recoverable time
- Sector sample rate was hardcoded to 60Hz instead of the rate derived from the file

**Time loss itself was validated as correct**: best lap matches the official iRacing result to 1 ms, and sector times match an independent interpolation method to within 0.011s.

**Still open (RR-021):** the `min_speed_spread_mph > 10` threshold is absolute mph and misfires on fast corners — 5 of 8 corners tripped it, including T13 at 14.9 mph spread on an 85.9 mph apex. Needs to become speed-relative. Treat spread-based coaching as unvalidated until then.

### 3. Standalone Race Results Processing (P3)
**Goal:** `tenths results "path/to/eventresult.json"` for races without telemetry.
- See `docs/TECH_DEBT.md` P3 section for spec

### 4. Lower coaching threshold to 0.1s (DONE — 2026-07-18)
Changed from 0.3s to 0.1s so distributed time loss across corners surfaces in Summary View.

### 5. iRacing OAuth2 (Phase 5 — future)
- Auto-pull race results (no manual CSV download)
- Full track catalog with turn positions for all circuits

---

## Key Documentation
- `docs/ARCHITECTURE_VISION.md` — Full product vision, phased roadmap
- `docs/HTML_REPORT_DESIGN.md` — Report features, Pit Wall theme spec
- `docs/WATCHER_ARCHITECTURE.md` — 3-tier watcher design
- `docs/COACHING_METRICS_DESIGN.md` — Morad-style coaching → Tenths metrics mapping
- `docs/TECH_DEBT.md` — Known issues + proposed fixes
- `docs/UX_IMPROVEMENTS.md` — UI/UX items (resolved + remaining)
- `docs/PROJECT_PLAN.md` — Phase status tracker

## Testing
```cmd
cd c:\Users\justi\Documents\Sim\Tenths
python -m pytest tests/ -v --tb=short
```

## Running
```cmd
# System tray (production)
pythonw -m tenths.cli tray

# CLI watch (development)
python -m tenths.cli watch

# Process specific file (supports paths with spaces)
python -m tenths.cli process "path\to\file.ibt"

# Generate master session index
python -m tenths.cli index
```

## Steering File
`.kiro/steering/tenths-development.md` in the Sim workspace enforces:
- Run tests after every change
- Tests must never just assert True
- Follow Pit Wall theme
- JS in report.py needs brace-matching care
