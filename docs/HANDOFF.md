# Tenths Development Handoff — Context for Next Session

## Current State (as of 2026-06-14)

### What Tenths Is
An iRacing telemetry analysis tool that auto-processes .ibt files and generates interactive HTML coaching reports. Runs as a Windows system tray app — zero-friction background service.

### Repository
- **Path:** `c:\Users\justi\Documents\Sim\Tenths`
- **GitHub:** `git@github.com:jgarbiso/Tenths.git`
- **Branch:** `main`
- **Version:** 0.9.0
- **Tests:** 106 passing (pytest), 8.5s runtime

### Architecture
```
tenths/
├── config.py              # Centralized config (auto-detects paths)
├── cli.py                 # CLI entry: watch, tray, process, report, summary, migrate
├── analyzer.py            # Core .ibt parser + all metrics
├── process.py             # Session notes orchestrator
├── report.py              # HTML report generator (inline JS/CSS, Leaflet + Chart.js)
├── summary.py             # session_summary.json generator + schema migration
├── track_map.py           # Track map file parser (% → turn names)
├── track_map_generator.py # Auto-generates skeleton track maps from GPS
├── results.py             # iRacing race result parser
├── incidents.py           # Incident forensics
└── service/
    ├── watcher.py         # File system watcher (watchdog, event-driven)
    ├── notifier.py        # Windows toast notifications (winotify)
    └── tray.py            # System tray app (pystray)
```

### Key Design Decisions
- **Pit Wall theme** — dark mode with specific color tokens (docs/HTML_REPORT_DESIGN.md)
- **Orbitron font** for hero numbers, Inter for UI, JetBrains Mono for data
- **Unified braking zones table** — one template for ALL car classes
- **Event-driven watcher** — watchdog (ReadDirectoryChangesW), zero CPU when idle
- **BELOW_NORMAL thread priority** during processing when iRacing may be running
- **Toast notification** by default, browser auto-open is opt-in (`--open` flag)
- **No git commit** by default (`--git` flag to opt-in)
- **Config auto-detects** `~/Documents/iRacing/telemetry` for any user

### What's Complete
- ✅ CLI Enhancement Tasks 1.1–1.7 (JSON contract, schema migration, track maps, metrics)
- ✅ HTML Report (map, charts, compare, brake release, brake points, steering)
- ✅ Watcher Tier 1 (CLI `tenths watch`)
- ✅ Watcher Tier 2 (toast notifications)
- ✅ Watcher Tier 3 (system tray app)
- ✅ Coaching metrics (Apex ±, Input Stability, Brake Duration, Corner Ranking, T2Peak, Thr On, Thr Lag, Brake Linearity)
- ✅ MVP prep (centralized config, no hardcoded paths, v0.9.0)

---

## NEXT STEPS (in priority order)

### 1. PyInstaller + Inno Setup Packaging
**Goal:** Single .exe installer that any iRacing user can download and run.

**Steps:**
1. Create `installer/tenths.spec` (PyInstaller spec file)
   - Bundle: tenths/ package, all deps, Python runtime, assets/tenths.ico, tracks/*.md
   - Entry point: `tenths/service/tray.py:main`
   - Flags: `--noconsole`, `--onefile` or `--onedir`
2. Test the .exe runs standalone (no Python installed)
3. Create `installer/tenths_setup.iss` (Inno Setup)
   - Install to `%LOCALAPPDATA%/Tenths/`
   - Start Menu entry, optional Desktop shortcut
   - Register startup key
   - Create uninstaller
4. Test on a clean VM or another PC

**Dependencies for packaging:**
- PyInstaller (`pip install pyinstaller`)
- Inno Setup (download from jrsoftware.org — not pip)

**Key files to include in bundle:**
- `assets/tenths.ico`
- `tracks/*.md` (all track maps)
- All Python packages in dependencies list

### 2. Coaching Sentences (Future iteration)
Auto-generate plain-English coaching text per corner:
- "T4: Your apex speed varies by ±17mph — find a consistent visual reference"
- "T1: Brake release is stepped (0.41) — work on progressive release"

### 3. iRacing OAuth2 (Phase 5)
- Auto-pull race results (no manual CSV download)
- Full track catalog with turn positions for all circuits

---

## Key Documentation
- `docs/ARCHITECTURE_VISION.md` — Full product vision, phased roadmap
- `docs/HTML_REPORT_DESIGN.md` — Report features, Pit Wall theme spec
- `docs/WATCHER_ARCHITECTURE.md` — 3-tier watcher design
- `docs/COACHING_METRICS_DESIGN.md` — Morad-style coaching → Tenths metrics mapping
- `docs/TECH_DEBT.md` — Known issues for future resolution
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

# Process specific file
python -m tenths.process "path\to\file.ibt"
```

## Steering File
`.kiro/steering/tenths-development.md` in the Sim workspace enforces:
- Run tests after every change
- Tests must never just assert True
- Follow Pit Wall theme
- JS in report.py needs brace-matching care
