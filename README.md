# Tenths

*Find your tenths.*

Tenths is an automated race engineer for iRacing. It runs quietly in your system tray, watches for new telemetry, and the moment a session ends it builds a visual coaching report that tells you **where you're losing time and why** — in plain English, no charts to decipher.

No accounts. Telemetry analysis and the Summary view run locally. The current Detailed view loads chart, map, and font assets from third-party CDNs, so it requires internet access for full functionality; fully offline Detailed reporting is tracked in the release remediation plan.

---

## For drivers

**→ [Getting Started Guide](docs/GETTING_STARTED.md)** — install, enable telemetry, and read your first report in about five minutes.

The short version:
1. Install `TenthsSetup.exe` (no admin needed, adds itself to your tray)
2. Enable iRacing telemetry (Alt+L in-sim, or `irsdkLogAll=1` in `app.ini` for always-on)
3. Drive
4. Click the notification when your session finishes — your report opens in the browser

### What you get

Each successfully processed watcher session produces one local HTML report with two views:

**Summary** (opens by default, built to read at a glance — even in VR):
- Hero numbers: best lap, recoverable time, delta vs your last session, lap count
- **Next Race Focus** — the single most important thing to fix, in plain English
- Top 3 time-loss corners, each with a coaching sentence and speed context
- Mini track map with your problem corners marked

**Detailed** (the full data):
- Interactive track heatmap (speed/brake coloring, rotatable)
- Stacked telemetry traces (brake/throttle, speed, steering)
- Lap selector + lap comparison with speed delta
- Brake-release shape curves with linearity scores
- Braking zones, corner variance, and lap tables
- Race result badge with iRating delta

Corner names come from a built-in database covering **450+ iRacing tracks** — no setup required.

---

## Highlights

- **Low-friction** — while Tenths is running, it watches for completed sessions and processes them automatically; startup recovery and retry handling are tracked release blockers
- **Coaching-first** — translates raw telemetry into "release the brake more progressively at T5," not just line charts
- **Progression tracking** — a master index of processed sessions; compare against your past self, session over session
- **Physics profiles in development** — GT4-specific diagnostics exist; broader metadata-driven class handling is required before public release
- **Local analysis** — track data and Summary coaching are bundled; the current Detailed view still loads CDN assets
- **Resource-conscious design** — event-driven watcher and low processing priority; formal CPU/RAM measurements remain pending

---

## For developers

### Requirements
- Python 3.10+
- Dependencies are declared in `pyproject.toml` (pyirsdk, pandas, numpy, watchdog, winotify, pystray, Pillow, PyYAML)

```cmd
python -m pip install -e .
```

### Running from source

```cmd
# System tray app (production entry point)
pythonw -m tenths.cli tray

# CLI watcher (foreground, with console output)
python -m tenths.cli watch          # notification only
python -m tenths.cli watch --open   # also auto-open reports

# Process pending .ibt files (notes + HTML report + JSON summary)
python -m tenths.cli process
python -m tenths.cli process "path\to\file.ibt"
python -m tenths.cli process --dry-run

# Generate a single report / summary
python -m tenths.cli report "path\to\file.ibt"
python -m tenths.cli summary "path\to\file.ibt"

# Master session index
python -m tenths.cli index

# Incident forensics (spin/contact/stop detection) for specific laps
python -m tenths.cli incident "path\to\file.ibt" 2,3,4

# Upgrade session_summary.json files to the current schema
python -m tenths.cli migrate

# Tests
python -m pytest tests/
```

### What gets generated

Watcher-generated sessions are stored under `telemetry/<car>/<track>/<date>/<time>/`. Manual and standalone CLI commands still have known date-level output inconsistencies tracked in `docs/RELEASE_REMEDIATION_PLAN.md`.

| File | Purpose |
|------|---------|
| `session_report.html` | Interactive visual report (Summary + Detailed) |
| `session_notes.md` | Markdown coaching notes |
| `session_summary.json` | Structured data contract (schema-versioned) |

A master `index.html` at the telemetry root lists all sessions with filters.

### Project structure

```
tenths/
├── cli.py                 # Entry point (tenths command)
├── config.py              # Centralized config, path/console setup
├── analyzer.py            # Core .ibt parser + all metrics
├── process.py             # Session-notes orchestrator (multi-session, results matching)
├── report.py              # HTML report generator (Summary + Detailed)
├── summary.py             # session_summary.json + schema migration
├── index_generator.py     # Master session browser
├── track_map.py           # Turn-name lookup (landmark DB + .md fallback)
├── track_map_generator.py # Skeleton track maps from GPS
├── results.py             # iRacing race-result parser (CSV/JSON)
├── incidents.py           # Incident forensics
├── data/                  # Bundled trackLandmarksData.json (450+ tracks)
└── service/
    ├── watcher.py         # File watcher (watchdog, event-driven)
    ├── notifier.py        # Windows toast notifications
    └── tray.py            # System tray app
```

### Configuration (optional env vars)
- `TENTHS_TELEMETRY_ROOT` — iRacing telemetry directory (auto-detected: `~/Documents/iRacing/telemetry`)
- `TENTHS_TRACKS_DIR` — override for track-map `.md` files

### Building the installer
See `installer/` — `tenths.spec` (PyInstaller) and `tenths_setup.iss` (Inno Setup). Run `python installer/build.py` (add `--full` to also build the installer, requires Inno Setup).

### Documentation
- `docs/GETTING_STARTED.md` — user onboarding
- `docs/ARCHITECTURE_VISION.md` — product vision & roadmap
- `docs/HTML_REPORT_DESIGN.md` — report design & theme
- `docs/COACHING_METRICS_DESIGN.md` — metrics → coaching mapping
- `docs/WATCHER_ARCHITECTURE.md` — watcher design
- `docs/RELEASE_REMEDIATION_PLAN.md` — canonical release blockers, implementation steps, tests, and acceptance criteria
- `docs/DISTRIBUTION_READINESS.md` — historical first distribution review
- `docs/TECH_DEBT.md` — known issues and historical plans

---

## License

MIT — see [LICENSE](LICENSE).
