# Tenths: Product Vision & Architecture

## What Tenths Is

An "Automated Data Engineer" for sim racers. Tenths goes beyond telemetry visualization by quantifying driver inputs into actionable, plain-English coaching to help users shave vital fractions of a second off their lap times.

The end-state UX is zero-friction: a background service (like Trading Paints) that auto-processes telemetry the moment a session ends and immediately surfaces a visual debrief — no manual steps, no file hunting.

---

## Current State (Phase 1 — Complete)

**What exists today:**
- Python CLI tool (`tenths process`, `tenths report`, `tenths analyze`)
- Parses .ibt files using pyirsdk + pandas
- Generates `session_notes.md` (markdown coaching report) per session
- Generates `session_report.html` (interactive visual report) per session
- Physics-aware braking analysis (GT4 vs Touring detection)
- 5 Stages of Braking metrics (T2Peak, Coast_Time, TurnIn_Brk%, Apex_Brake, Lugging)
- GPS track mapping with braking zone coordinates
- Corner variance & time loss analysis
- Race result auto-matching by subsession_id
- Multi-session per day support
- Git auto-commit

**Stack:** Python 3.14, pyirsdk, pandas, numpy, PyYAML. No server, no database, no accounts.

---

## Phase 2: Local Web Dashboard (Next)

**Goal:** `tenths serve` — FastAPI backend serving the HTML report as a local web app with session switching.

- FastAPI serves session data as JSON API
- Browser UI (the existing HTML report, upgraded to fetch from API instead of embedded JSON)
- Session selector (browse by car/track/date)
- Lap comparison overlays (best vs worst, this session vs previous)
- No cloud, no accounts — purely local

---

## Phase 3: Background Service (Trading Paints Model)

**Goal:** Zero-friction auto-processing. Install once, forget about it.

| Component | Technology | Role |
|-----------|-----------|------|
| Background service | Python (PyInstaller .exe) or Windows Service | Watches telemetry folder for new .ibt files, auto-processes on session end |
| System tray | pystray or equivalent | Minimal UI: "Processing...", "Ready — click to view" |
| Auto-launch | Windows startup registration | Starts with PC, sits in tray |
| Notification | Windows toast notification | "Session processed — P3 at Winton, 1:30.965 PB!" |
| Browser pop-up | Default browser → localhost dashboard | One-click to see the full visual report |

**Key challenge:** Detecting when a session is truly "done" (file handle released by iRacing, not just a qualifying → race transition). Solution: watch for file handle release + minimum file size + 5-second cooldown after last write.

**Race results:** With OAuth2 integration (see Phase 5), the service can auto-pull results from iRacing's API once the session subsession_id is known from the .ibt header. Without OAuth2, it continues using the current approach (auto-match from Downloads folder if user exports manually).

---

## Phase 4: Cloud Platform & Sharing

**Goal:** Multi-user, team sharing, pro-comparison features.

| Tier | Technology | Role |
|------|-----------|------|
| Edge (local) | Python background service | Parses .ibt locally, uploads compressed JSON summary |
| Cloud backend | FastAPI + PostgreSQL (JSONB) | Stores session summaries, serves API |
| Frontend | Next.js (React) + Chart.js/ECharts | Full web dashboard, team views, historical trends |
| Auth | OAuth2 (iRacing identity or standalone) | User accounts, team management |

**Architectural trade-off:** Only JSON summaries are uploaded (not raw .ibt files). This keeps cloud storage costs near zero but means retroactive analysis for new metrics requires the desktop client to re-parse local files on app update.

**Features unlocked by cloud:**
- Share sessions with teammates / coach
- Compare your braking to a reference lap (faster driver same car/track)
- Leaderboard-style "how does my T2Peak compare to the field"
- Historical progression graphs across an entire season
- Team dashboards (e.g., "all drivers at Winton this week")

---

## Phase 5: iRacing Data API Integration

**Purpose:** Auto-pull race results, car/track metadata, and (eventually) other drivers' data for comparison.

**Current status:** OAuth2 required since Dec 2025. `iracingdataapi` package installed but non-functional (legacy auth retired). See `docs/IRACING_API.md` for full research.

**Implementation plan:**
- OAuth2 flow with `password_limited` grant for headless server use
- Cloud-side CRON job: daily sync of car list, track list, series schedules → `tenths_master_config.json`
- Desktop client boot sync: downloads latest config on launch
- Per-session: auto-fetch race result by subsession_id after session end

**What we get from .ibt header already (no API needed):**
- Car display name, track display name, track length
- Driver name, iRating, car class
- Subsession ID, series ID, event type
- Redline RPM, idle RPM, fuel capacity, gearbox type
- Track GPS coordinates, weather

**What requires the API:**
- Full race results for other drivers (positions, gaps, incidents)
- Historical iRating progression
- Series schedules and track rotation
- Official vs unofficial classification

---

## Phase 6: Real-Time Audio Coaching (Future)

**Goal:** In-race feedback — audio callouts based on live telemetry.

| Component | Approach |
|-----------|----------|
| Data source | iRacing live UDP telemetry stream (not .ibt) |
| Trigger | Sector-line crossing or corner-exit detection |
| Analysis | Compare current corner metrics to previous best |
| Output | Windows TTS or CrewChief custom macro trigger |

**Example callout:** *"T11: brake release was 0.3 seconds late"* or *"ABS count is trending up — check tire pressure"*

**Trade-off vs. CrewChief:** CrewChief already provides spotter + basic pace feedback. Tenths real-time would focus specifically on technique coaching (braking shape, throttle application, consistency) rather than race strategy. Could potentially integrate as a CrewChief plugin rather than standalone.

**This is the longest-horizon feature and may never be built** — post-session analysis covers 90% of the coaching value.

---

## Proprietary Metrics (Implemented + Planned)

### Implemented ✅

| Metric | Stage | Description |
|--------|-------|-------------|
| T2Peak | Stage 2: Initial Hit | Time from >5% brake to peak pressure |
| Coast_Time | Stage 1: Transition | Gap between throttle lift and brake application |
| TurnIn_Brk% | Stage 4: Release | Brake pressure at steering commitment (>15° turn-in) |
| Apex_Brake | Stage 5: Apex | Brake % at minimum speed point |
| [Lugging] | Stage 5: Apex | RPM below powerband at apex (GT4: <4000, Touring: <3500) |
| Brk2Shft | Stage 3: Modulation | Time from brake application to first downshift |
| MaxDS_RPM | Stage 3: Modulation | Peak RPM during downshift sequence |
| Trail_Combined_Load | — | Lateral G while brake >30% (trail braking quality) |
| Corner_Variance | — | Time loss per corner vs theoretical best |

### Planned (Not Yet Implemented)

| Metric | Description |
|--------|-------------|
| Time_to_100% | Delta from 0% brake at apex to 100% throttle (exit aggression) |
| Steer_Jerk | Rate of change in steering angle mid-corner (tire scrubbing detection) |
| Brake_Linearity | How smooth is the brake release curve (step vs linear vs convex) |
| Throttle_Hesitation | Time spent between 20-80% throttle on exit (indecision) |

---

## UI Dashboard Components (Current + Planned)

### Built ✅ (HTML Report)

- Interactive track heatmap (speed/brake coloring, rotation, corner labels)
- Stacked telemetry traces (Brake+Throttle, Speed)
- Hover sync between map and charts
- Race result badge (position, iRating, podium colors)
- Braking zones table (car-class-specific)
- Corner variance table
- Lap summary table
- Session stats grid

### Planned

- Tire health heatmap (chassis graphic with temp gradients)
- Consistency scatter plot (corners × time loss)
- ABS trend line chart (using `lap_abs_totals` array)
- Lap time progression sparkline
- Multi-lap overlay comparison
- Session history timeline (progression across dates)

---

## Build vs. Fork Decision

An analysis of the open-source `iracing-telemetry-analyzer` concluded:

| Attribute | Open-source tool | Tenths |
|-----------|-----------------|--------|
| Focus | Local, private, self-comparison | Community-driven, cloud-sharing, pro-comparisons |
| Analysis | Basic data visualization | Automated coaching (proprietary metrics, plain-English) |
| Tech Stack | Browser-based local HTML/JS viewer | Background service + API + real-time capable |

**Decision: "Borrow, Don't Build On"** — Tenths remains standalone to protect proprietary coaching logic and enable complex cloud + real-time features. Study open-source tools for file detection patterns and session grouping inspiration only.
