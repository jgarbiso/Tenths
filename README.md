# Tenths

*Find your tenths.*

A telemetry analysis and coaching tool for iRacing. Parses `.ibt` files, generates session notes with braking diagnostics, GPS track mapping, corner variance analysis, and driver progression tracking.

## Features

- **Physics-aware braking analysis** — GT4 vs Touring car detection with class-specific diagnostics
- **5 Stages of Braking metrics** — T2Peak, Coast Time, Turn-In Brake %, Apex Brake %
- **GPS track mapping** — real coordinates for every braking zone
- **Corner variance & time loss** — identifies priority corners automatically
- **Track map integration** — maps telemetry percentages to actual turn names
- **Session notes generation** — complete markdown coaching reports, zero AI tokens
- **HTML visual reports** — interactive track heatmap, telemetry charts, hover sync (see below)
- **Multi-session per day** — practice + qualifying + race combined in one notes file
- **Race result auto-matching** — finds iRacing results by subsession_id in Downloads
- **Incident forensics** — spin detection, contact evidence, GPS location
- **Car/track metadata from .ibt header** — no API needed, works offline

## Quick Start

```cmd
cd c:\Users\justi\Documents\Sim\Tenths

# Watch for new sessions and auto-process (notification when done)
python -m tenths.cli watch

# Watch and also auto-open report in browser
python -m tenths.cli watch --open

# Process all pending .ibt files (generates notes + HTML report + JSON summary)
python -m tenths.process

# Process a specific .ibt file
python -m tenths.process "c:\Users\justi\Documents\iRacing\telemetry\_archive\bmwm2csr_winton national 2026-06-06 22-26-36.ibt"

# Dry run (preview without writing)
python -m tenths.process --dry-run

# Generate just the HTML visual report
python -m tenths.cli report "path\to\file.ibt"

# Generate just the JSON summary
python -m tenths.cli summary "path\to\file.ibt"

# Upgrade all session_summary.json files to current schema
python -m tenths.cli migrate

# Analyze a specific file (prints coaching report to stdout)
python -m tenths.analyzer "path\to\file.ibt"

# Run tests
python -m pytest tests/
```

## What Gets Generated

When you process a session, three files are created in `telemetry/<car>/<track>/<date>/`:

| File | Purpose |
|------|---------|
| `session_notes.md` | Markdown coaching report with tables and findings |
| `session_report.html` | Interactive visual report — open in any browser |
| `session_summary.json` | Structured data contract for dashboards and progression |

## HTML Visual Report

The `session_report.html` is a self-contained interactive report. Open in any browser, no server needed.

**Features:**
- **Track heatmap** — GPS trace colored by speed or brake pressure, rotatable to match iRacing view
- **Per-lap brake points overlay** — shows braking consistency with spread metrics
- **Telemetry traces** — stacked panels: Brake+Throttle, Speed, Steering (MoTeC-style)
- **Lap selector** — switch between any valid lap, all charts update
- **Lap comparison** — overlay two laps with speed delta panel (green = faster, red = slower)
- **Brake Release Shape panel** — SVG curves showing release quality per corner with linearity scores
- **Race result badge** — prominent P# with iRating delta and podium colors
- **Data tables** — braking zones (Thr On, Thr Lag metrics), corner variance, lap summary
- **Corner labels + direction arrow** — turn names on the track map with travel direction
- **ABS sparkline** — visual trend of ABS hits across the session

Opens in any browser, no server needed. Uses the "Pit Wall" dark theme (F1 engineering screen aesthetic).

## How It Works

1. **Find** — scans telemetry root for unprocessed `.ibt` files
2. **Group** — groups files by car/track/date (multi-session support)
3. **Analyze** — runs full analysis on each valid session (lap times, ABS, braking zones, GPS, tire temps)
4. **Match** — auto-finds race results from Downloads by subsession_id
5. **Map** — applies turn names from track map files
6. **Generate** — produces complete `session_notes.md` with all sessions for the day
7. **Archive** — moves `.ibt` files to `_archive/`
8. **Commit** — git add + commit + push

## Data Sources

| Data | Source | Notes |
|---|---|---|
| Car display name | `.ibt` file header (`CarScreenName`) | No API needed |
| Track display name | `.ibt` file header (`TrackDisplayName`) | No API needed |
| Session type | `.ibt` file header (`EventType`) | Practice/Qualify/Race auto-detected |
| Turn names | Track map files (`tracks/*.md`) | One-time manual creation per track |
| Race results | iRacing CSV/JSON exports | Auto-matched by subsession_id |
| Telemetry data | `.ibt` channels (60Hz) | Speed, brake, throttle, GPS, temps, etc. |

## Project Structure

```
tenths/
├── __init__.py          # Version
├── cli.py               # Entry point (tenths command)
├── analyzer.py          # Core analysis engine + analyze() API
├── process.py           # Session notes orchestrator (multi-session, results matching)
├── report.py            # HTML visual report generator (track map, charts, tables)
├── track_map.py         # Track map file parser (% → turn names)
├── results.py           # iRacing race result parser (CSV + JSON)
├── incidents.py         # Incident forensics (spin/contact detection)
└── setup_iracing_cache.py  # iRacing API cache (OAuth2 required, not yet functional)
```

## Requirements

- Python 3.10+
- pyirsdk
- pandas
- numpy
- PyYAML

```cmd
python -m pip install pyirsdk pandas pyyaml
```

## Track Maps

Track maps are markdown files that map telemetry percentages to turn names. Located in `tracks/`:
- `fuji_nochicane.md`
- `midohio_full.md`
- `navarra_speedlong.md`
- `winton_national.md`

To create a new track map:
1. Run a session at the track (Tenths will use percentages as fallback)
2. Get a screenshot of the iRacing track map
3. Cross-reference GPS coordinates from the session with the map
4. Create a markdown file with the turn mapping table

## Configuration

Environment variables (optional):
- `TENTHS_TELEMETRY_ROOT` — path to iRacing telemetry directory (default: `c:\Users\justi\Documents\iRacing\telemetry`)
- `TENTHS_SIM_ROOT` — path to SimRacing repo root (default: `c:\Users\justi\Documents\Sim`)
- `TENTHS_TRACKS_DIR` — path to track map files

## License

MIT
