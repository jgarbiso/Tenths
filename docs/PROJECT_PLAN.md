# Session Notes Automation — Project Plan

## Goal

Replace the manual AI-driven telemetry processing workflow with a single Python script that generates complete `session_notes.md` files identical in quality to what Kiro produces — zero tokens, run from a terminal.

---

## Current Workflow (AI-driven, ~10-12K tokens per session)

1. User says "process today's practice/race"
2. Kiro finds .ibt files
3. Kiro runs `analyze_ibt.py`, reads stdout (~3K tokens in)
4. Kiro reads track map file + previous session notes (~3K tokens in)
5. Kiro writes full `session_notes.md` (~4K tokens out)
6. Kiro updates track reference file, archives files, git commits

## Target Workflow (script-driven, zero tokens)

```cmd
cd c:\Users\justi\Documents\iRacing\telemetry
python tools\generate_session_notes.py
```

Or with race results:
```cmd
python tools\generate_session_notes.py --race-result "C:\Users\justi\Downloads\eventresult_12345_0.csv"
```

---

## Architecture

```
tools/
├── analyze_ibt.py              ← REFACTOR: add analyze() that returns dict
├── generate_session_notes.py   ← NEW: orchestrator script
├── track_map.py                ← NEW: parse track reference files
├── baseline.py                 ← NEW: load previous session data
├── incident_check.py           ← KEEP: manual incident forensics
├── parse_result.py             ← KEEP: race result extraction
├── process_session.py          ← DEPRECATED: replaced by generate_session_notes.py
└── SESSION_NOTES_AUTOMATION.md ← This document
```

---

## Phase 1: Practice Session Processor

**STATUS: COMPLETE**

### What Phase 1 produces:

- Session header with car/track names from .ibt header (no API needed)
- Session type auto-detection (Practice/Qualify/Race from .ibt header)
- Multi-session per day support (practice + qualifying + race in one file)
- Race result auto-matching (finds CSV/JSON by subsession_id in Downloads)
- Lap summary table (selective — first, milestones, cleanest, best, final laps)
- Braking zones table with turn names from track map
- Trail braking table with turn names
- Corner variance table with turn names and priority flags
- GPS Track Position Map
- Tire temps table
- GT4 Brake Shape progress
- 5 Stages of Braking metrics (Coast_Time, TurnIn_Brk%)
- Key Findings (rule-based: PBs, records, priority corners, brake shape status)
- Targets for Next Session (auto-generated from data)
- Files table
- Archive .ibt to `_archive/`
- Copy race result file to session folder
- Git commit + push

### What Phase 1 does NOT do:

- Race results context (SOF, position, iRating change)
- Race highlights narrative ("NEW CLEANEST EVER")
- Coaching Summary (What's Working / What Needs Work)
- Session Progression history across multiple dates
- Incident analysis
- Multiple sessions in one notes file (practice + race)

---

## Phase 2: Polish & Advanced Features

**STATUS: IN PROGRESS**

| Task | Description | Status |
|------|-------------|--------|
| 1.1 | `session_summary.json` output | ✅ Done |
| 1.2 | Schema versioning + migration | ✅ Done |
| **1.6** | **Auto-generate skeleton track maps** | ✅ Done |
| 1.3 | Time_to_100% + Throttle_Hesitation | ✅ Done (Thr On, Thr Lag) |
| 1.4 | Steer_Jerk + Brake_Linearity | Not started |
| 1.5 | Session progression summary | Not started |
| 1.7 | Testing framework | ✅ Done (68 tests) |

### Remaining items:

1. De-duplicate header info (race context appears twice)
2. Session Progression history table (loads all previous session_notes for same track)
3. Coaching Summary section (What's Working / What Needs Work — rule-based)
4. Race Highlights callouts (NEW PB, NEW CLEANEST at top level)
5. Auto-detect incidents (laps >5s off pace or car stopped) — flag without narrative
6. Negative Brk2Shft values → show "—"
7. Targets use turn names not percentages
8. Fix: same-date runs overwrite previous session notes (should merge/append)
9. iRacing OAuth2 integration for auto-pulling race results
10. Web frontend (FastAPI + HTML/JS) — `tenths serve`

---

## Component Design

### 1. `analyze_ibt.py` Refactor

Add a public `analyze(filepath)` function that returns structured data:

```python
def analyze(filepath):
    """Returns dict with all analysis results."""
    return {
        'vehicle': str,
        'venue': str,
        'car_class': 'GT4' | 'Touring',
        'track_length_m': float,
        'valid_laps': [int],
        'best_lap': int,
        'worst_lap': int,
        'lap_results': [
            {'lap': int, 'time': float, 'abs': int, 'max_speed_mph': float, ...}
        ],
        'abs_trend': {'early_avg': float, 'late_avg': float, 'delta': float},
        'braking_zones': [
            {'pct': float, 'dist_m': float, 'lat': float, 'lon': float,
             'entry_mph': float, 'min_mph': float, 'max_brake': float,
             'abs': int, 't2peak': float, 'brake_to_shift': float,
             'max_ds_rpm': float, 'apex_brake': float, 'notes': [str]}
        ],
        'trail_braking': [
            {'pct': float, 'brake': float, 'lat_g': float, 'yaw': float, 'diagnosis': str}
        ],
        'corner_variance': [
            {'pct': float, 'avg': float, 'best': float, 'loss': float, 'std': float}
        ],
        'tire_temps': {
            'LF': {'inner': float, 'mid': float, 'outer': float},
            ...
        },
        'gps_trace': [
            {'pct': int, 'dist': float, 'lat': float, 'lon': float, 'speed_mph': float}
        ],
    }
```

The existing `main()` stays unchanged for standalone use.

### 2. `track_map.py` — Track Map Parser

```python
def load_track_map(track_name):
    """Load track map from Sim/tracks/<track>.md, return turn lookup."""
    # Returns: {'zones': [{'pct_min': 12, 'pct_max': 16, 'turn': 'T1-T2', 'name': 'TGR Corner'}]}

def get_turn_name(track_map, pct):
    """Given a track percentage, return the closest turn name."""
    # Matches within ±3% tolerance
    # Returns: 'T1-T2 TGR Corner' or 'T4 (23%)' if no match
```

Parses the markdown table format used in all track files.

### 3. `baseline.py` — Previous Session Loader

```python
def load_baseline(car, track):
    """Find most recent session_notes.md for this car/track, extract key metrics."""
    # Searches: telemetry/<car>/<track>/*/session_notes.md
    # Returns: {
    #   'pb_time': float,
    #   'cleanest_abs': int,
    #   't2peak_by_zone': {pct: float},
    #   'date': str,
    # }
    # Returns None if no previous session exists
```

### 4. `generate_session_notes.py` — Orchestrator

```python
"""
Generate Session Notes — Automated Telemetry Processing
=========================================================
Finds unprocessed .ibt files, analyzes them, generates complete
session_notes.md with turn names, baselines, and coaching flags.

Usage:
    python tools/generate_session_notes.py                    # process all pending
    python tools/generate_session_notes.py --dry-run          # preview without writing
    python tools/generate_session_notes.py "path/to/file.ibt" # process specific file

Phase 2:
    python tools/generate_session_notes.py --race-result "path/to/result.csv"
"""
```

---

## Lap Selection Heuristics

Not all laps go in the table. Rules:

1. **Always include:** First valid lap, best lap, cleanest lap (lowest ABS with time < best+3s)
2. **Include if notable:** Any lap that sets a new session-best at the time it was set
3. **Include the last 3-5 laps** (show final pace)
4. **Skip** laps that are >10% slower than best (incidents/resets)
5. **Cap at 10-12 rows** — if >12 laps qualify, keep first, milestone laps, and last few

---

## Key Findings Generation Rules

Automated commentary based on data:

| Condition | Finding |
|---|---|
| First session at this track | "First session — X seconds gained over N laps" |
| New PB (vs baseline) | "NEW PB: X (prev: Y)" |
| New cleanest ABS (vs baseline) | "NEW CLEANEST: X ABS (prev: Y)" |
| Corner with >0.5s loss | "T___ is HIGH PRIORITY — Xs loss" |
| T2Peak at/below 0.4s | "T___ brake shape AT TARGET" |
| T2Peak improving vs baseline | "T___ improving (Xs → Ys)" |
| ABS trend negative | "ABS improving through session (-X)" |
| ABS trend positive >50 | "ABS worsening — fatigue or pushing too hard" |
| Oversteer risk flags | "Oversteer risk at T___ — release brake before rotation" |
| Best laps at end of session | "Best laps came late — still finding time" |

---

## Targets Generation Rules

Auto-generated from current data:

1. **Lap time target:** current best - 0.5s (round to nearest 0.5)
2. **ABS target for highest-ABS zone:** current / 2 (or <30 if already low)
3. **T2Peak target:** any zone >0.5s → target is current - 0.2s
4. **Corner variance:** any HIGH priority → target "under 0.3s"
5. **Consistency:** if spread >1.5s → target "within 1.0s"

---

## Track File Update Logic

Append a row to the Performance History table:

```markdown
| Jun 2 | Practice | 1:32.491 | 164 | First session — 5.4s improvement |
```

Logic:
- Parse the existing table to find where to insert
- Detect if this is a new PB or cleanest record → bold the value
- Notes: auto-generate from key findings (first session, PB, cleanest, incident)

---

## File Organization

```
Input:  c:\Users\justi\Documents\iRacing\telemetry\*.ibt (unprocessed files in root)
Output: c:\Users\justi\Documents\iRacing\telemetry\<car>\<track>\<date>\session_notes.md
Archive: c:\Users\justi\Documents\iRacing\telemetry\_archive\<original filename>.ibt
Track:  c:\Users\justi\Documents\Sim\Sim\tracks\<track>.md (updated)
Git:    c:\Users\justi\Documents\Sim (commit + push)
```

---

## Testing Plan

1. Re-process the Mid-Ohio Jun 2 .ibt (still in `_archive`) and compare output against the manually-written session_notes.md
2. Re-process a Fuji .ibt and verify turn names match, baselines compare correctly
3. Verify git commit message format
4. Test with missing track map (should use percentages as fallback)
5. Test first-session-at-track detection

---

## Known Issues (Phase 1 Polish)

Items identified from testing against the Mid-Ohio Jun 2 session. Data output is correct — these are display/formatting issues.

| # | Issue | Fix |
|---|---|---|
| 1 | Car display name shows raw filename (`bmwm4evogt4`) instead of friendly name (`BMW M4 EVO GT4`) | Add a `CAR_DISPLAY_NAMES` lookup dict in generate_session_notes.py |
| 2 | Track display name shows title-cased directory (`Midohio Full`) instead of proper name (`Mid-Ohio Sports Car Course, Full Course`) | Pull display name from the track map .md file header (first `# ` line) |
| 3 | "NEW PB" triggers when re-running against existing session (PB == baseline PB) | Only flag NEW PB if `best_time < baseline['pb_time']` (strict less-than, not equal) |
| 4 | Negative Brk2Shft values displayed (e.g., `-0.47s`) — these are measurement artifacts where the downshift happened before brake application | Show "—" for negative values |
| 5 | Targets section uses percentages (`62% time loss`) instead of turn names (`T10 time loss`) | Pass track_map to `generate_targets()` and use `get_turn_name()` |
| 6 | Missing "### Learning Curve" sub-heading for first-visit sessions | Add sub-heading when `is_first_session` is True |
| 7 | No "first session improvement" line when baseline exists (correct behavior, but confusing on re-runs) | Add `--force-first` flag for re-processing, or detect from lap count/time spread |
| 8 | Lap Notes column shows empty strings as spaces — minor formatting | Only output Notes column content if non-empty |

---

## Dependencies

- Python 3.14.5 (installed)
- pyirsdk (installed)
- pandas (installed)
- numpy (installed)
- No new dependencies needed
