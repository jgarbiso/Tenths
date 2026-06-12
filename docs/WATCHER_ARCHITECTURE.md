# Tenths Watcher — Windows Application Architecture

## Overview

The Tenths Watcher is the delivery mechanism that connects the analysis engine to the driver. It transforms Tenths from a CLI tool into a zero-friction background service that automatically processes telemetry and surfaces visual reports the moment a session ends.

## User Experience Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. User launches Tenths (or it starts with Windows)                │
│  2. Icon appears in system tray (idle state)                        │
│  3. User races in iRacing                                           │
│  4. Session ends → iRacing writes .ibt file and releases handle     │
│  5. Watcher detects completed file → icon changes to "processing"   │
│  6. Processing completes (5-30 seconds)                             │
│  7. Windows toast notification: "P3 at Winton — 1:30.965 PB!"      │
│  8. User clicks notification → report opens in browser              │
│  9. Icon returns to idle state                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Architecture Tiers

### Tier 1: CLI Watcher (`tenths watch`) — Implement First

A single Python command that runs in the foreground, watches for files, processes them, and opens the report. This is the MVP that delivers the core UX.

```
                    ┌─────────────────┐
                    │  tenths watch   │
                    │  (foreground)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌──────────────┐ ┌────────────┐ ┌────────────────┐
    │ File Watcher │ │  Processor │ │ Report Opener  │
    │ (watchdog)   │ │ (existing) │ │ (webbrowser)   │
    └──────────────┘ └────────────┘ └────────────────┘
```

**Dependencies:** `watchdog` (file system events)
**Runs as:** Terminal command — user opens terminal, runs `tenths watch`, minimizes window
**Output:** Console log + opens browser on completion

### Tier 2: Notification-Enhanced Watcher — Add Next

Same as Tier 1 but with Windows toast notifications so the user doesn't need to watch the terminal.

```
    ┌──────────────────────────────────────────────────────────┐
    │                    tenths watch                           │
    ├──────────────┬────────────┬──────────────┬───────────────┤
    │ File Watcher │ Processor  │ Notifier     │ Report Opener │
    │ (watchdog)   │ (existing) │ (winotify)   │ (webbrowser)  │
    └──────────────┴────────────┴──────────────┴───────────────┘
```

**New dependency:** `winotify` (Windows toast notifications)
**Behavior:** Toast appears in Windows notification center with session summary. Click action opens report.

### Tier 3: System Tray Application — Final Form

Full background application with system tray icon, no terminal window required.

```
    ┌─────────────────────────────────────────────────────────────────┐
    │                    Tenths Service                                │
    ├──────────┬──────────────┬────────────┬───────────┬──────────────┤
    │ Tray UI  │ File Watcher │ Processor  │ Notifier  │ iRacing      │
    │ (pystray)│ (watchdog)   │ (existing) │ (winotify)│ Detector     │
    │          │              │            │           │ (psutil)     │
    └──────────┴──────────────┴────────────┴───────────┴──────────────┘
          │                                                    │
          │  ← State updates (idle/processing/error)           │
          │  ← Menu: Open Dashboard, Recent, Pause, Exit       │
          │                                                    │
          │                                    Priority yield ─┘
          │                                    when iRacing active
```

**New dependencies:** `pystray`, `psutil`, `Pillow` (for icon)
**Packaging:** PyInstaller → single .exe, no Python needed
**Distribution:** Inno Setup installer → Start Menu, startup registration

---

## Component Design

### 1. File Watcher (`tenths/service/watcher.py`)

**Responsibility:** Detect when a new .ibt file is complete and ready for processing.

**Detection Logic:**
```python
class TelemetryWatcher:
    """Watches TELEMETRY_ROOT for new .ibt files."""

    # Detection criteria (ALL must be true):
    # 1. File extension is .ibt
    # 2. File size > 1MB (MIN_SESSION_SIZE)
    # 3. File modification time stable for 5 seconds (no more writes)
    # 4. File handle is not locked by iRacing (can open exclusively)

    # Qualifying → Race transition handling:
    # - After processing a file, if another .ibt appears for same car/track
    #   within 5 minutes, treat as separate session
    # - Read EventType from .ibt header to confirm session boundary
```

**File System Events:**
- Use `watchdog.observers.Observer` to monitor `TELEMETRY_ROOT`
- Listen for `FileCreatedEvent` and `FileModifiedEvent` with `.ibt` filter
- Debounce: track last-modified time, only trigger when stable for 5 seconds

**Edge Cases:**
- iRacing crash mid-session → file handle released but data may be incomplete → check file size > 1MB
- Multiple iRacing instances (unlikely but possible) → process all valid files
- Network drives or junctions → `watchdog` handles these transparently on Windows
- False starts (join session, immediately leave) → filtered by 1MB minimum

### 2. Processor (`tenths/service/processor.py`)

**Responsibility:** Orchestrate the full pipeline for a detected file.

```python
class SessionProcessor:
    """Processes a completed .ibt file through the full Tenths pipeline."""

    def process(self, filepath: str) -> ProcessResult:
        """
        Steps:
        1. Parse filename → file_info (car, track, date, time)
        2. Analyze .ibt → data dict (analyzer.analyze())
        3. Load/generate track map
        4. Find race result (Downloads folder scan)
        5. Generate session_notes.md
        6. Generate session_report.html
        7. Generate session_summary.json (with progression)
        8. Archive .ibt to _archive/
        9. Git commit (if configured)

        Returns:
            ProcessResult with session_dir, best_lap_time, race_result, etc.
        """
```

**This is essentially the existing `process.py` main() refactored into a callable class** with a structured return value instead of print statements.

### 3. Notifier (`tenths/service/notifier.py`)

**Responsibility:** Inform the user that processing is complete.

```python
class SessionNotifier:
    """Sends notifications to the user about processed sessions."""

    def notify_complete(self, result: ProcessResult):
        """
        Windows toast notification with:
        - Title: "Tenths — Session Processed"
        - Body: "{Race/Practice} at {Track} — {best_lap_time}"
        - If race: "P{pos}/{field} | iR {delta:+d}"
        - If PB: "🏆 NEW PB!"
        - Click action: open session_report.html in browser
        """

    def notify_error(self, filepath: str, error: str):
        """
        Error notification:
        - Title: "Tenths — Processing Failed"
        - Body: filename + error summary
        """
```

**Toast notification library:** `winotify` (lightweight, pure Python, supports click actions)

### 4. iRacing State Detector (`tenths/service/iracing_state.py`)

**Responsibility:** Know whether iRacing is actively running a session.

```python
class IRacingState:
    """Detects iRacing process state for CPU yielding."""

    def is_running(self) -> bool:
        """Check if iRacingSim64DX11.exe is in process list."""

    def is_in_session(self) -> bool:
        """Check if iRacing shared memory indicates active session."""
        # Optional: use pyirsdk to check SessionInfo
        # Simpler: just check process exists
```

**Purpose:** When iRacing is running, lower the processing thread priority so analysis doesn't cause frame drops. Still process immediately on file completion — just at lower CPU priority.

### 5. Tray UI (`tenths/service/tray.py`) — Tier 3 Only

**Responsibility:** System tray icon with state indication and context menu.

```python
class TenthsTray:
    """System tray application."""

    # Icon states:
    # - Idle (grey/dim icon)
    # - Processing (animated or blue icon)
    # - Error (red icon)

    # Context menu:
    # - "Open Last Report" → opens most recent session_report.html
    # - "Recent Sessions" → submenu of last 5 sessions
    # - "───────────"
    # - "Pause Processing" → toggle
    # - "Start with Windows" → toggle (registry key)
    # - "───────────"
    # - "Exit"
```

---

## Directory Structure

```
tenths/
├── service/
│   ├── __init__.py
│   ├── watcher.py          # File system monitoring
│   ├── processor.py        # Pipeline orchestration
│   ├── notifier.py         # Windows toast notifications
│   ├── iracing_state.py    # Process/priority detection
│   ├── tray.py             # System tray UI (Tier 3)
│   └── main.py             # Entry point for packaged app (Tier 3)
├── cli.py                  # Adds 'watch' command (Tier 1)
└── ...existing modules...
```

---

## Implementation Sequence

### Phase 2A: `tenths watch` (Tier 1) — Can use tonight

| Step | What | Effort |
|------|------|--------|
| 1 | Create `tenths/service/watcher.py` with `TelemetryWatcher` | 20 min |
| 2 | Create `tenths/service/processor.py` wrapping existing pipeline | 15 min |
| 3 | Add `tenths watch` CLI command that starts watcher | 10 min |
| 4 | Console output: "Watching... Detected... Processing... Done! Opening report." | 5 min |
| 5 | Auto-open `session_report.html` in browser on completion | 5 min |

**Total: ~1 hour. Usable immediately.**

### Phase 2B: Toast Notifications (Tier 2) — Same day

| Step | What | Effort |
|------|------|--------|
| 6 | Add `winotify` dependency | 2 min |
| 7 | Create `tenths/service/notifier.py` | 15 min |
| 8 | Notification click → open report | 10 min |

**Total: ~30 min additional.**

### Phase 2C: System Tray (Tier 3) — Later

| Step | What | Effort |
|------|------|--------|
| 9 | Add `pystray`, `psutil` dependencies | 5 min |
| 10 | Create `tenths/service/tray.py` | 45 min |
| 11 | Create `tenths/service/iracing_state.py` | 15 min |
| 12 | Integrate watcher + tray + priority yielding | 30 min |
| 13 | PyInstaller packaging | 30 min |
| 14 | Inno Setup installer | 30 min |
| 15 | Windows startup registration | 10 min |

**Total: ~3 hours additional.**

---

## Resource & Performance Constraints

| Metric | Requirement |
|--------|-------------|
| RAM (idle) | < 30 MB |
| RAM (processing) | < 200 MB (pandas + numpy) |
| CPU (idle) | ~0% (event-driven, not polling) |
| CPU (processing) | Standard priority, or BELOW_NORMAL when iRacing active |
| Startup time | < 2 seconds to tray icon visible |
| Processing time | < 30 seconds for typical 50MB .ibt |

---

## Configuration

Stored in `%LOCALAPPDATA%/Tenths/config.json` (Tier 3) or environment variables (Tier 1):

```json
{
    "telemetry_root": "c:\\Users\\justi\\Documents\\iRacing\\telemetry",
    "auto_open_report": true,
    "notifications_enabled": true,
    "start_with_windows": false,
    "git_auto_commit": true,
    "cpu_yield_when_racing": true,
    "min_file_size_bytes": 1000000,
    "file_stable_seconds": 5
}
```

---

## Error Handling Strategy

| Error | Behavior |
|-------|----------|
| .ibt file corrupted/too small | Log warning, skip, notify if configured |
| No valid laps in session | Log, archive file, no report generated |
| Track map missing | Auto-generate skeleton (Task 1.6 handles this) |
| Race result not found | Continue without — report still generates |
| Git push fails | Log error, don't block processing |
| File watcher disconnects | Attempt reconnect every 10 seconds |
| Unhandled exception in processing | Catch, log traceback, notify error, continue watching |

---

## Security Considerations

- No network access required (all local processing)
- No elevated permissions needed (user-space file watching)
- Registry access only for startup registration (HKCU, no admin)
- No sensitive data transmitted anywhere
- File paths stored in config are user-specific

---

## Testing Strategy

| Layer | Approach |
|-------|----------|
| Watcher | Mock file system events, test debounce logic, test size/handle checks |
| Processor | Already tested (existing 85 tests cover the pipeline) |
| Notifier | Mock winotify calls, verify message formatting |
| Integration | Create temp .ibt file, verify full flow: detect → process → output files exist |
