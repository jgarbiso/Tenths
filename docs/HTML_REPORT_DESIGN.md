# Tenths HTML Report — Design Document

## Overview

A self-contained HTML file generated per session alongside `session_notes.md`. Opens in any browser with no server, no build step, no dependencies to install. The report provides a visual, interactive complement to the markdown notes — track map with speed/brake heatmap, synced telemetry charts, and result tables.

## Status: POC v1 — BUILT ✅

All core features implemented and working. Tested against Winton (Touring/M2 CS) and Mid-Ohio (GT4/M4 EVO) sessions.

---

## What Was Built

### Files Created/Modified

| File | Change |
|------|--------|
| `tenths/report.py` | **NEW** — HTML report generator (self-contained, inline CSS/JS) |
| `tenths/analyzer.py` | Modified `_extract_gps_trace()` — now returns 200 dense points with Speed/Brake/Throttle/Gear |
| `tenths/process.py` | Added import + auto-generates `session_report.html` during normal processing |
| `tenths/cli.py` | Added `tenths report <file.ibt>` command |

### CLI Usage

```bash
# Generate report for a specific .ibt file
tenths report "path/to/file.ibt"

# Or it generates automatically during normal processing
tenths process
```

Output: `session_report.html` in the session directory alongside `session_notes.md`.

---

## Architecture

### Data Flow

```
.ibt file
    → analyzer.analyze()       → structured dict (200-point GPS trace)
    → report.generate_report() → session_report.html (self-contained)
    → process.generate_notes() → session_notes.md (unchanged)
```

### Libraries (loaded via CDN in the HTML)

| Library | Version | Purpose |
|---------|---------|---------|
| Leaflet | 1.9.4 | Track map rendering |
| Chart.js | 4.4.0 | Telemetry line charts |

No framework. Vanilla JS. No build step. ~70KB output HTML files.

### Data Embedding

All session data is embedded as a JSON blob in a `<script>` tag:
```html
<script>const DATA = { ...all session data... };</script>
```

---

## Current Features

### 1. Track Heatmap (Leaflet)

- **200-point GPS trace** at 0.5% lap distance intervals
- **Two visualization modes** (toggle buttons):
  - Speed: Green (fast) → Amber (coast) → Red (slow/braking)
  - Brake: Grey (off) → Red (max pressure)
- **Rotation controls** — ↶/↷ buttons rotate the track 15° per click to match iRacing overhead view
- **Corner name labels** — permanent labels at each braking zone from track map data
- **Direction arrow** — white arrow showing travel direction near start/finish
- **S/F marker** — white dot with "S/F" label at start/finish line
- **Pure black background** — no tiles, no internet needed, works offline
- **Hover cursor** — white dot follows mouse position, synced with charts

### 2. Telemetry Charts (Chart.js — Stacked Panels)

Three stacked panels (MoTeC-style layout):

| Panel | Height | Channels | Colors |
|-------|--------|----------|--------|
| Brake / Throttle | 180px | Brake %, Throttle % (0–100 scale) | Red (brake), Green (throttle) |
| Speed | 150px | Speed in mph | Orange |
| Steering | 150px | Steering angle in degrees (centered on 0°) | Blue |

- **Y-axis gridlines**: Brake/Throttle at 0%, 25%, 50%, 75%, 100%. Speed every 10 mph. Steering every 45°.
- **No smoothing on brake/throttle** (tension: 0) — shows exact pedal input
- **Slight smoothing on speed/steering** (tension: 0.15) — naturally smoother signals
- **Crosshair plugin** — vertical white line synced across all panels on hover
- **X-axis**: Lap Distance % (only shown on bottom panel)

### 3. Lap Selector

- Dropdown in the Telemetry section header listing all valid laps with time and best-lap marker
- Selecting a lap switches:
  - Track map heatmap to that lap's speed/brake data
  - All three telemetry chart panels to that lap's traces
- Brake Points overlay is unaffected (always shows all laps)
- Data: dense 200-point GPS trace extracted for every valid lap (stored in `gps_traces` dict keyed by lap number)

### 4. Hover Sync System

- Single shared float `hoverPct` (0–100, LapDistPct)
- Both map and charts write to it on hover, both read via `requestAnimationFrame` loop
- Map: repositions cursor marker + updates cursor opacity
- Charts: custom crosshair plugin draws vertical line at position
- Info bar: fixed bar at bottom shows position, speed, brake%, throttle%
- **60fps, zero lag** — no events, no pub/sub, just a number and a render tick

### 5. Per-Lap Brake Points Overlay

- "Brake Points" toggle button on the track map
- When active: renders one colored dot per valid lap at each braking zone's entry point (where Brake first crosses 15%)
- Color gradient: blue (early laps) → amber (late laps)
- Spread metric (±Xm) displayed at each zone cluster
- Legend bar below the map showing the color scale
- Always shows ALL laps regardless of lap selector — consistency tool
- Custom Leaflet pane (z-index 650) ensures dots render above the track line

### 6. Race Result Badge

- **Prominent header position** — large P# with field size and iRating delta
- **Color-coded**: Green for iR gains, red for losses
- **Podium accents**: Gold (P1), Silver (P2), Bronze (P3) coloring on the position number
- **Glow effect** on podium finishes

### 5. Data Tables

| Table | Data |
|-------|------|
| Braking Zones | All zones with turn names, entry/min speed, ABS, car-class-specific metrics |
| Corner Variance | Time loss per corner, sorted by priority |
| Lap Summary | All valid laps with time, ABS, max speed — best lap highlighted |

- GT4 tables show T2Peak, Coast, Turn-In Brake
- Touring tables show Brk2Shft, MaxDS RPM, Apex RPM
- Color coding: red for ABS hits, amber for medium priority, red for high

### 6. Session Stats Grid

Six stat cards: Valid Laps, Cleanest ABS, Track Length, Car Class, ABS Trend (with color), Brake Zones count.

---

## Visual Theme: "Pit Wall" (MANDATORY for all Tenths UI)

Inspired by F1 race engineering data screens — the professional debrief look.
**This is the canonical Tenths color scheme. All future UI work (web frontend, dashboards, exports) must use this palette.**

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-base` | `#0a0a0f` | Page background (near-black with blue tint) |
| `--bg-surface` | `#12141f` | Card/panel backgrounds (dark navy) |
| `--bg-surface-raised` | `#1a1d2b` | Elevated elements, hover states |
| `--border` | `#2a2d3a` | Borders, dividers (subtle steel blue) |
| `--text-primary` | `#e8eaf0` | Headings, key data |
| `--text-secondary` | `#8890a4` | Labels, descriptions, muted text |
| `--accent-green` | `#00e676` | Throttle, gains, "good" states |
| `--accent-red` | `#ff1744` | Braking, ABS, losses, "bad" states |
| `--accent-amber` | `#ffab00` | Speed trace, coast/transition, warnings |
| `--accent-blue` | `#448aff` | iRating, info, timing data, links |
| `--accent-gold` | `#ffd740` | P1 / podium gold |
| `--accent-silver` | `#b0bec5` | P2 / podium silver |
| `--accent-bronze` | `#ff8f00` | P3 / podium bronze |

### Telemetry Trace Colors (specific to charts)

| Channel | Color | Hex |
|---------|-------|-----|
| Throttle | Green | `#00e676` |
| Brake | Red | `#ff1744` |
| Speed | Orange/Amber | `#ffab00` |

### Typography
- Headings: `Inter`, `system-ui`, sans-serif
- Data/numbers: `JetBrains Mono`, `Fira Code`, monospace
- Font sizes: 13px base, 11px table cells, 32px hero numbers

### Design Principles
1. Data density over whitespace — drivers want information, not padding
2. Color carries meaning — green is always good, red is always attention-needed
3. Numbers are the hero — large, monospace, high-contrast
4. Consistent with professional motorsport data tools (Atlas, MoTeC, Pi Toolbox)
5. Celebrate the wins — podium finishes get visual flair

---

## Layout (Actual)

```
┌─────────────────────────────────────────────────────────────────────┐
│  BMW M2 CS Racing          1:30.965         P4 / 11 cars  iR +40    │
│  Winton - National — Date   BEST LAP                                │
├────────────────────────────────────┬────────────────────────────────┤
│                                    │  7        31                    │
│   TRACK MAP                        │  VALID    CLEANEST             │
│   [↶ 90° ↷] [Speed] [Brake]       │  2.95km   Touring              │
│                                    │  +11      5                    │
│   (rotatable heatmap with          │  ABS      BRAKE ZONES          │
│    corner labels + direction)      │                                │
├────────────────────────────────────┴────────────────────────────────┤
│  BRAKE / THROTTLE  ═══════════════════════════════════════  180px    │
│  (green throttle + red brake, shared 0-100% scale)                  │
├─────────────────────────────────────────────────────────────────────┤
│  SPEED  ═══════════════════════════════════════════════════  150px   │
│  (orange, own scale, every 10mph gridline)                          │
├──────────────────────────────┬──────────────────────────────────────┤
│  BRAKING ZONES table         │  CORNER VARIANCE table               │
├──────────────────────────────┴──────────────────────────────────────┤
│  LAP SUMMARY table (full width)                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Track Map Rotation

The track map supports interactive rotation to match iRacing's overhead view:
- Default: 90° clockwise from north-up GPS orientation
- User can click ↶/↷ buttons to rotate ±15° per click
- Rotation is applied mathematically to GPS coordinates before rendering
- All elements (track line, markers, labels, arrows) rotate together

**Future**: Store preferred rotation per track (track_id → rotation_degrees) so it remembers.

---

## Future Improvements (Not in POC v1)

- [ ] Multi-lap comparison (overlay best vs worst)
- [ ] Lap selector dropdown
- [ ] Gear channel on chart (as colored background band)
- [ ] Trail braking visualization on track map (brake zones colored by lat-G)
- [ ] Per-track rotation memory (store in track map files)
- [ ] `tenths serve` — FastAPI backend serving interactive dashboard
- [ ] Lap time progression sparkline
- [ ] Tire temp heatmap visualization
- [ ] Print-friendly mode (Ctrl+P)
- [ ] Keyboard shortcuts (S/B toggle, arrow keys for rotation)
- [ ] Store rotation preference per track_id

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-07 | Chart.js over Recharts | No React/build step needed for static HTML |
| 2026-06-07 | Pure black map background | Works offline, cleaner than tiles |
| 2026-06-07 | 200-point GPS trace | One sample every ~15m, smooth corners |
| 2026-06-07 | Pit Wall theme (Option A) | Professional F1 data screen aesthetic |
| 2026-06-07 | Celebrate the wins | Prominent race badge with podium colors |
| 2026-06-07 | Stacked panels over single chart | MoTeC-style, industry standard readability |
| 2026-06-07 | Throttle=green, Speed=orange | Brake=red/Throttle=green is natural pairing |
| 2026-06-07 | Interactive rotation | Each track has different ideal orientation |
| 2026-06-11 | Steering trace added (blue) | Third panel, degrees centered on 0° |
| 2026-06-11 | Per-lap brake points overlay | Consistency visualization, all laps clustered |
| 2026-06-11 | Lap selector dropdown | Switch any lap for map+charts, brake points unaffected |
| 2026-06-11 | All-laps dense trace extraction | 200 pts × N laps stored in gps_traces dict |
