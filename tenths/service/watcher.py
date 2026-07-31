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

from tenths.applog import get_logger

log = get_logger(__name__)

# Minimum file size to process (1MB) — below this is a false start
MIN_FILE_SIZE = 1_000_000
# Seconds of no modification before considering file "done"
STABLE_SECONDS = 5

# Retry policy for a failed session. Processing can fail for transient reasons —
# the file is still locked, a result CSV is half written, the disk is briefly
# busy — so a single failure must not discard the session permanently.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (10, 45)   # delay before attempt 2, then attempt 3

# Artifacts that must exist before a session counts as processed. The source
# .ibt is only archived once all of these are on disk.
REQUIRED_ARTIFACTS = ("session_report.html", "session_notes.md", "session_summary.json")


class FileState:
    """Lifecycle of one .ibt within a watcher run."""
    PENDING = "pending"          # queued, or waiting for a retry
    IN_PROGRESS = "in_progress"  # a worker thread owns it
    DONE = "done"                # all artifacts written
    FAILED = "failed"            # retries exhausted; left in place for the user


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

    def __init__(self, telemetry_root=None, auto_open=True, on_complete=None):
        from tenths.config import TELEMETRY_ROOT as DEFAULT_ROOT
        self._root = telemetry_root or os.environ.get('TENTHS_TELEMETRY_ROOT', DEFAULT_ROOT)
        self._auto_open = auto_open
        self._on_complete = on_complete
        self._observer = None
        self._handler = None
        self._running = False
        # filepath -> {state, attempts, next_attempt, error}
        self._states = {}
        self._state_lock = threading.RLock()
        self._notifier = None

    # ── Processing state ─────────────────────────────────────────────────────

    def _claim(self, filepath):
        """Try to take ownership of a file for processing.

        Returns True if this caller should process it now. Dedupes duplicate
        filesystem events and concurrent workers, while still allowing a
        retry after a transient failure.
        """
        now = time.time()
        with self._state_lock:
            record = self._states.get(filepath)
            if record is None:
                self._states[filepath] = {
                    "state": FileState.IN_PROGRESS, "attempts": 1,
                    "next_attempt": None, "error": None,
                }
                return True
            if record["state"] in (FileState.IN_PROGRESS, FileState.DONE, FileState.FAILED):
                return False
            # PENDING: only start once the backoff has elapsed
            if record["next_attempt"] and now < record["next_attempt"]:
                return False
            record["state"] = FileState.IN_PROGRESS
            record["attempts"] += 1
            record["next_attempt"] = None
            return True

    def _mark_success(self, filepath):
        with self._state_lock:
            record = self._states.setdefault(filepath, {"attempts": 1})
            record.update(state=FileState.DONE, next_attempt=None, error=None)

    def _mark_failure(self, filepath, error, stage="processing"):
        """Record a failure and decide whether to retry.

        Returns (will_retry, attempts).
        """
        with self._state_lock:
            record = self._states.setdefault(
                filepath, {"attempts": 1, "next_attempt": None, "error": None})
            attempts = record.get("attempts", 1)
            record["error"] = f"{stage}: {error}"
            if attempts < MAX_ATTEMPTS:
                delay = RETRY_BACKOFF_SECONDS[min(attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
                record["state"] = FileState.PENDING
                record["next_attempt"] = time.time() + delay
                return True, attempts
            record["state"] = FileState.FAILED
            record["next_attempt"] = None
            return False, attempts

    def _due_retries(self):
        """Files whose backoff has elapsed and which should be retried."""
        now = time.time()
        with self._state_lock:
            return [
                path for path, record in self._states.items()
                if record.get("state") == FileState.PENDING
                and record.get("next_attempt") is not None
                and now >= record["next_attempt"]
            ]

    def state_of(self, filepath):
        """Current state string for a file, or None if unknown. For tests/status."""
        with self._state_lock:
            record = self._states.get(filepath)
            return record.get("state") if record else None

    def failed_files(self):
        """Sources that exhausted their retries and remain unprocessed."""
        with self._state_lock:
            return {path: record.get("error")
                    for path, record in self._states.items()
                    if record.get("state") == FileState.FAILED}

    def _get_notifier(self):
        if self._notifier is None:
            from tenths.service.notifier import SessionNotifier
            self._notifier = SessionNotifier()
        return self._notifier

    def _ensure_watch_root(self):
        """Ensure the telemetry folder exists before watching.

        Returns True if the folder is ready, False if it couldn't be found/created.
        On a fresh PC (or before iRacing telemetry is enabled) the folder may not
        exist yet — watchdog would raise if we scheduled against a missing path.
        """
        if os.path.isdir(self._root):
            return True
        # Try to create it — iRacing will populate it once telemetry is enabled
        try:
            os.makedirs(self._root, exist_ok=True)
            return True
        except OSError:
            return False

    def start(self):
        """Start watching. Blocks until interrupted (Ctrl+C)."""
        if self._running:
            log.warning("Watcher is already running; ignoring duplicate start().")
            return

        if not self._ensure_watch_root():
            log.error("iRacing telemetry folder not found: %s. Enable telemetry in "
                      "iRacing (Options > Telemetry) and restart Tenths.", self._root)
            try:
                self._get_notifier().notify_error(
                    "Telemetry folder not found",
                    "Enable telemetry in iRacing (Options > Telemetry), then restart Tenths.",
                )
            except Exception as exc:
                log.warning("Could not show the error notification: %s", exc)
            return

        from tenths.applog import log_path
        log.info("Tenths Watch — monitoring: %s", self._root)
        log.info("  Auto-open report: %s", self._auto_open)
        log.info("  Min file size: %.0f MB", MIN_FILE_SIZE / 1_000_000)
        log.info("  Stability wait: %ds   Retries: %d", STABLE_SECONDS, MAX_ATTEMPTS)
        log.info("  Log file: %s", log_path())

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
                self._retry_due_files()
        except KeyboardInterrupt:
            log.info("Stopping watcher...")
        finally:
            self._running = False
            try:
                self._observer.stop()
                self._observer.join(timeout=10)
            except Exception as exc:
                log.warning("Error while stopping the observer: %s", exc)
            outstanding = self.failed_files()
            if outstanding:
                log.warning("%d session(s) could not be processed and remain in %s:",
                            len(outstanding), self._root)
                for path, error in outstanding.items():
                    log.warning("  %s — %s", os.path.basename(path), error)
            log.info("Watcher stopped.")

    def _retry_due_files(self):
        """Re-dispatch files whose retry backoff has elapsed."""
        for filepath in self._due_retries():
            if not os.path.exists(filepath):
                # Removed or archived in the meantime — nothing to retry
                with self._state_lock:
                    record = self._states.get(filepath)
                    if record:
                        record["state"] = FileState.FAILED
                        record["next_attempt"] = None
                log.info("Not retrying %s: the file is no longer present.",
                         os.path.basename(filepath))
                continue
            log.info("Retrying %s", os.path.basename(filepath))
            self._on_file_ready(filepath)

    def stop(self):
        """Stop the watcher (for programmatic use)."""
        self._running = False

    def _on_file_ready(self, filepath):
        """Called when a .ibt file is complete and ready to process."""
        if not self._claim(filepath):
            return

        filename = os.path.basename(filepath)
        try:
            size_mb = os.path.getsize(filepath) / 1_000_000
        except OSError:
            size_mb = 0.0
        attempt = self._states.get(filepath, {}).get("attempts", 1)
        suffix = f" (attempt {attempt} of {MAX_ATTEMPTS})" if attempt > 1 else ""
        log.info("Detected %s — %.1f MB at %s%s",
                 filename, size_mb, datetime.now().strftime('%H:%M:%S'), suffix)

        # Process in a thread at lower priority
        t = threading.Thread(target=self._process_file, args=(filepath,), daemon=True)
        t.start()

    def _handle_failure(self, filepath, error, stage):
        """Log a failure, retry if attempts remain, otherwise surface it."""
        filename = os.path.basename(filepath)
        will_retry, attempts = self._mark_failure(filepath, error, stage)
        if will_retry:
            delay = RETRY_BACKOFF_SECONDS[min(attempts - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
            log.warning("Processing failed for %s during %s (attempt %d of %d): %s "
                        "— retrying in %ds",
                        filename, stage, attempts, MAX_ATTEMPTS, error, delay,
                        exc_info=isinstance(error, BaseException))
            return

        log.error("Giving up on %s after %d attempts. Last failure during %s: %s. "
                  "The .ibt has been left in place so it can be retried.",
                  filename, attempts, stage, error,
                  exc_info=isinstance(error, BaseException))
        try:
            self._get_notifier().notify_error(filename, f"{stage}: {error}")
        except Exception as notify_error:
            log.warning("Could not show the error notification: %s", notify_error)

    def _process_file(self, filepath):
        """Run the full Tenths pipeline on the file.

        Wrapped so that any failure is logged, retried while attempts remain,
        and surfaced to the user once they are exhausted. A session is only
        marked done after every required artifact exists on disk.
        """
        stage = "startup"
        try:
            self._run_pipeline(filepath)
        except Exception as exc:
            self._handle_failure(filepath, exc, stage="processing")
        except BaseException as exc:  # KeyboardInterrupt/SystemExit during shutdown
            log.warning("Processing of %s interrupted: %s",
                        os.path.basename(filepath), exc)
            self._mark_failure(filepath, exc, stage="interrupted")

    def _run_pipeline(self, filepath):
        """The actual pipeline. Raises on failure; the caller handles retries."""
        # Lower thread priority so we don't compete with iRacing
        self._set_low_priority()

        log.info("Processing %s", os.path.basename(filepath))
        start_time = time.time()

        # Import here to avoid circular deps and keep idle memory low
        from tenths.analyzer import analyze
        from tenths.process import parse_filename, find_race_result, TELEMETRY_ROOT
        from tenths.track_map import load_track_map
        from tenths.track_map_generator import generate_skeleton_track_map, write_skeleton_track_map
        from tenths.report import generate_report
        from tenths.summary import generate_session_summary, write_session_summary
        from tenths.process import generate_day_notes, load_baseline

        file_info = parse_filename(filepath)
        if not file_info:
            # Not a transient problem — retrying will not change the filename.
            log.warning("Skipping %s: filename does not match the expected "
                        "iRacing pattern, so car/track/date cannot be determined.",
                        os.path.basename(filepath))
            self._mark_success(filepath)   # nothing more to attempt
            return

        data = analyze(filepath)
        if not data:
            # Also permanent: an .ibt with no valid laps will never gain any.
            log.info("Skipping %s: no valid laps found (too short, or the car "
                     "never completed a clean lap).", os.path.basename(filepath))
            self._mark_success(filepath)
            return

        car = file_info['car']
        track = file_info['track']
        date = file_info['date']

        # Track map (load or auto-generate)
        track_map = load_track_map(track)
        if not track_map and data.get('braking_zones'):
            si = data.get('session_info', {})
            try:
                skeleton = generate_skeleton_track_map(data, si)
                written = write_skeleton_track_map(skeleton, track.lower().replace(' ', '_'))
                if written:
                    log.info("Auto-generated track map: %s", os.path.basename(written))
                    track_map = load_track_map(track)
            except Exception as exc:
                # Cosmetic: turn names fall back to percentages.
                log.warning("Could not auto-generate a track map for %s: %s", track, exc)

        # Race result — optional, must never block the telemetry report
        race_result = None
        si = data.get('session_info', {})
        try:
            result_file = find_race_result(si)
            if result_file:
                from tenths.results import parse_result
                race_result = parse_result(result_file, my_cust_id=si.get('driver_id'))
        except Exception as exc:
            log.warning("Could not read the race result for %s: %s — continuing "
                        "without finishing position or iRating.",
                        os.path.basename(filepath), exc)

        # Output directory — include session time so each session gets its own folder
        session_dir = os.path.join(TELEMETRY_ROOT, car, track, date, file_info['time'])
        os.makedirs(session_dir, exist_ok=True)

        # 1. Session notes
        baseline = load_baseline(car, track)
        notes_content = generate_day_notes(
            [(file_info, data, race_result)], car, track, date, track_map, baseline)
        notes_path = os.path.join(session_dir, "session_notes.md")
        with open(notes_path, 'w', encoding='utf-8') as f:
            f.write(notes_content)

        # 2. HTML report — each session gets its own report (never overwrite).
        # Summary + progression are computed first so the Summary View has them.
        from tenths.summary import compute_progression as _compute_progression
        summary = generate_session_summary(data, file_info, track_map, race_result)
        progression = _compute_progression(summary, session_dir)

        report_html = generate_report(data, file_info, track_map, race_result,
                                      progression=progression)
        report_path = os.path.join(session_dir, "session_report.html")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_html)

        # 3. JSON summary (write_session_summary re-computes progression internally)
        write_session_summary(summary, session_dir)

        # Every required artifact must exist before the source is archived.
        missing = [name for name in REQUIRED_ARTIFACTS
                   if not os.path.exists(os.path.join(session_dir, name))]
        if missing:
            raise RuntimeError(
                f"expected artifacts were not written to {session_dir}: {missing}")

        elapsed = time.time() - start_time
        best_time = summary['best_lap']['time_formatted']
        laps = summary['total_valid_laps']
        log.info("Done in %.1fs — %d laps, best %s", elapsed, laps, best_time)
        log.info("Report: %s", report_path)

        # Notification — nonfatal, but logged rather than swallowed
        try:
            from tenths.service.notifier import format_race_result
            is_pb = False
            if summary.get('progression'):
                is_pb = bool(summary['progression'].get('alltime_best', {}).get('is_new_pb'))
            self._get_notifier().notify_complete(
                best_time=best_time,
                laps=laps,
                track_name=summary.get('track', {}).get('name', track),
                session_type=summary.get('session', {}).get('type', 'Practice'),
                report_path=report_path,
                race_result=format_race_result(summary),
                is_pb=is_pb,
            )
        except Exception as exc:
            log.warning("Session processed, but the notification failed: %s", exc)

        # Master index — nonfatal, can be rebuilt with `tenths index`
        try:
            from tenths.index_generator import generate_master_index
            generate_master_index()
        except Exception as exc:
            log.warning("Could not regenerate the master index: %s "
                        "— run `tenths index` to rebuild it.", exc)

        if self._auto_open:
            try:
                webbrowser.open(f'file:///{report_path.replace(os.sep, "/")}')
            except Exception as exc:
                log.warning("Could not open the report in a browser: %s", exc)

        # Archive the source only now that everything is safely on disk
        import shutil
        archive_dir = os.path.join(TELEMETRY_ROOT, "_archive")
        os.makedirs(archive_dir, exist_ok=True)
        destination = os.path.join(archive_dir, os.path.basename(filepath))
        try:
            shutil.move(filepath, destination)
            log.info("Archived: _archive/%s", os.path.basename(filepath))
        except (OSError, shutil.Error) as exc:
            # Outputs exist, so this session is not lost. Do not fail the run.
            log.warning("Could not archive %s: %s — the report was still created, "
                        "but the .ibt may be picked up again.",
                        os.path.basename(filepath), exc)

        self._mark_success(filepath)
        if self._on_complete:
            try:
                self._on_complete(report_path)
            except Exception as exc:
                log.warning("Completion callback failed: %s", exc)

    @staticmethod
    def _set_low_priority():
        """Set current thread to BELOW_NORMAL priority on Windows."""
        try:
            # BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetPriorityClass(handle, 0x00004000)
        except Exception:
            pass  # Non-critical — just means we run at normal priority
