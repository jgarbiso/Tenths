"""
Tenths File Watcher — Resource-Efficient Telemetry Detection
==============================================================
Watches the iRacing telemetry directory for new .ibt files.
Designed to be invisible on a sim racing PC:
- Event-driven (not polling) — zero CPU while idle
- Only activates when a file STOPS being written
- Processing runs at BELOW_NORMAL priority when iRacing is active
- Tiny memory footprint (~15MB idle)

Usage:
    from tenths.service.watcher import TelemetryWatcher
    watcher = TelemetryWatcher()
    watcher.start()  # blocks until Ctrl+C
"""

import os
import sys
import time
import threading
import webbrowser
import ctypes
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Minimum file size to process (1MB) — below this is a false start
MIN_FILE_SIZE = 1_000_000
# Seconds of no modification before considering file "done"
STABLE_SECONDS = 5


class IBTHandler(FileSystemEventHandler):
    """Handles .ibt file creation events."""

    def __init__(self, on_file_ready):
        super().__init__()
        self._on_file_ready = on_file_ready
        self._pending = {}  # filepath -> last_modified_time
        self._lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.ibt'):
            self._track_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.ibt'):
            self._track_file(event.src_path)

    def _track_file(self, filepath):
        """Mark a file as being actively written."""
        with self._lock:
            self._pending[filepath] = time.time()

    def check_pending(self):
        """Check if any pending files are ready (stable + large enough).
        Called periodically from the stability checker thread.
        """
        ready = []
        now = time.time()
        with self._lock:
            for filepath, last_mod in list(self._pending.items()):
                if now - last_mod >= STABLE_SECONDS:
                    # File hasn't been modified for STABLE_SECONDS
                    if os.path.exists(filepath) and os.path.getsize(filepath) >= MIN_FILE_SIZE:
                        # Verify we can open it exclusively (not locked by iRacing)
                        if self._can_open_exclusive(filepath):
                            ready.append(filepath)
                            del self._pending[filepath]
                    else:
                        # Too small or gone — discard
                        del self._pending[filepath]

        for filepath in ready:
            self._on_file_ready(filepath)

    @staticmethod
    def _can_open_exclusive(filepath):
        """Check if the file handle is not locked by another process."""
        try:
            with open(filepath, 'rb') as f:
                # If we can open it, iRacing has released the handle
                return True
        except (IOError, PermissionError):
            return False


class TelemetryWatcher:
    """Watches telemetry directory and auto-processes completed .ibt files.

    Resource design:
    - watchdog uses ReadDirectoryChangesW (Windows native API) — no polling
    - Stability checker runs every 2 seconds (minimal timer, not busy-wait)
    - Processing thread runs at BELOW_NORMAL priority
    """

    def __init__(self, telemetry_root=None, auto_open=True):
        from tenths.config import TELEMETRY_ROOT as DEFAULT_ROOT
        self._root = telemetry_root or os.environ.get('TENTHS_TELEMETRY_ROOT', DEFAULT_ROOT)
        self._auto_open = auto_open
        self._observer = None
        self._handler = None
        self._running = False
        self._processed = set()  # track files we've already handled this session

    def start(self):
        """Start watching. Blocks until interrupted (Ctrl+C)."""
        print(f"Tenths Watch — Monitoring: {self._root}")
        print(f"  Auto-open report: {self._auto_open}")
        print(f"  Min file size: {MIN_FILE_SIZE / 1_000_000:.0f} MB")
        print(f"  Stability wait: {STABLE_SECONDS}s")
        print(f"  Press Ctrl+C to stop.\n")

        self._handler = IBTHandler(self._on_file_ready)
        self._observer = Observer()
        self._observer.schedule(self._handler, self._root, recursive=False)
        self._observer.start()
        self._running = True

        # Stability checker — lightweight timer, not a busy loop
        try:
            while self._running:
                time.sleep(2)  # Check every 2 seconds — negligible CPU
                self._handler.check_pending()
        except KeyboardInterrupt:
            print("\nStopping watcher...")
        finally:
            self._observer.stop()
            self._observer.join()
            print("Watcher stopped.")

    def stop(self):
        """Stop the watcher (for programmatic use)."""
        self._running = False

    def _on_file_ready(self, filepath):
        """Called when a .ibt file is complete and ready to process."""
        # Dedup — don't process same file twice
        if filepath in self._processed:
            return
        self._processed.add(filepath)

        filename = os.path.basename(filepath)
        print(f"\n{'─'*60}")
        print(f"  Detected: {filename}")
        print(f"  Size: {os.path.getsize(filepath) / 1_000_000:.1f} MB")
        print(f"  Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'─'*60}")

        # Process in a thread at lower priority
        t = threading.Thread(target=self._process_file, args=(filepath,), daemon=True)
        t.start()

    def _process_file(self, filepath):
        """Run the full Tenths pipeline on the file."""
        # Lower thread priority so we don't compete with iRacing
        self._set_low_priority()

        try:
            print(f"  Processing...")
            start_time = time.time()

            # Import here to avoid circular deps and keep idle memory low
            from tenths.analyzer import analyze
            from tenths.process import parse_filename, find_race_result, TELEMETRY_ROOT
            from tenths.track_map import load_track_map
            from tenths.track_map_generator import generate_skeleton_track_map, write_skeleton_track_map
            from tenths.report import generate_report
            from tenths.summary import generate_session_summary, write_session_summary
            from tenths.process import generate_day_notes, load_baseline

            # Analyze
            data = analyze(filepath)
            if not data:
                print(f"  ⚠ No valid laps — skipping.")
                return

            file_info = parse_filename(filepath)
            if not file_info:
                print(f"  ⚠ Could not parse filename — skipping.")
                return

            car = file_info['car']
            track = file_info['track']
            date = file_info['date']

            # Track map (load or auto-generate)
            track_map = load_track_map(track)
            if not track_map and data.get('braking_zones'):
                si = data.get('session_info', {})
                skeleton = generate_skeleton_track_map(data, si)
                track_slug = track.lower().replace(' ', '_')
                written = write_skeleton_track_map(skeleton, track_slug)
                if written:
                    print(f"  Auto-generated track map: {os.path.basename(written)}")
                    track_map = load_track_map(track)

            # Race result
            race_result = None
            si = data.get('session_info', {})
            result_file = find_race_result(si)
            if result_file:
                from tenths.results import parse_result
                race_result = parse_result(result_file)

            # Output directory — include session time so each session gets its own folder
            session_time = file_info['time']  # e.g., "20-18-58"
            session_dir = os.path.join(TELEMETRY_ROOT, car, track, date, session_time)
            os.makedirs(session_dir, exist_ok=True)

            # Generate all outputs
            # 1. Session notes
            baseline = load_baseline(car, track)
            sessions = [(file_info, data, race_result)]
            notes_content = generate_day_notes(sessions, car, track, date, track_map, baseline)
            notes_path = os.path.join(session_dir, "session_notes.md")
            with open(notes_path, 'w', encoding='utf-8') as f:
                f.write(notes_content)

            # 2. HTML report — each session gets its own report (never overwrite)
            # Compute summary + progression before report generation so Summary View has it
            from tenths.summary import compute_progression as _compute_progression
            summary = generate_session_summary(data, file_info, track_map, race_result)
            progression = _compute_progression(summary, session_dir)

            report_html = generate_report(data, file_info, track_map, race_result, progression=progression)
            report_path = os.path.join(session_dir, "session_report.html")
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_html)

            # 3. JSON summary (write_session_summary re-computes progression internally)
            write_session_summary(summary, session_dir)

            elapsed = time.time() - start_time
            best_time = summary['best_lap']['time_formatted']
            laps = summary['total_valid_laps']

            print(f"  ✓ Done in {elapsed:.1f}s — {laps} laps, best: {best_time}")
            print(f"  → {report_path}")

            # Send toast notification
            try:
                from tenths.service.notifier import SessionNotifier, format_race_result
                notifier = SessionNotifier()
                track_name = summary.get('track', {}).get('name', track)
                session_type = summary.get('session', {}).get('type', 'Practice')
                race_info = format_race_result(summary)
                is_pb = summary.get('progression', {}).get('alltime_best', {}).get('is_new_pb', False) if summary.get('progression') else False
                notifier.notify_complete(
                    best_time=best_time,
                    laps=laps,
                    track_name=track_name,
                    session_type=session_type,
                    report_path=report_path,
                    race_result=race_info,
                    is_pb=is_pb,
                )
            except Exception as e:
                print(f"  ⚠ Notification failed: {e}")

            # Regenerate master index so new session appears immediately
            try:
                from tenths.index_generator import generate_master_index
                generate_master_index()
            except Exception:
                pass  # Non-critical — index can be rebuilt manually

            # Auto-open report in browser
            if self._auto_open:
                webbrowser.open(f'file:///{report_path.replace(os.sep, "/")}')

            # Archive the .ibt
            import shutil
            archive_dir = os.path.join(TELEMETRY_ROOT, "_archive")
            os.makedirs(archive_dir, exist_ok=True)
            shutil.move(filepath, os.path.join(archive_dir, os.path.basename(filepath)))
            print(f"  Archived: _archive/{os.path.basename(filepath)}")

        except Exception as e:
            print(f"  ✗ Error: {e}")
            import traceback
            traceback.print_exc()

    @staticmethod
    def _set_low_priority():
        """Set current thread to BELOW_NORMAL priority on Windows."""
        try:
            # BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetPriorityClass(handle, 0x00004000)
        except Exception:
            pass  # Non-critical — just means we run at normal priority
