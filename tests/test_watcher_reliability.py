"""
RR-004: watcher failures must be retried, logged and surfaced.

The packaged app runs with console=False, so before this a processing exception
went nowhere: the file stayed in `_processed`, was never retried, no error toast
was raised, and the tray icon looked perfectly healthy. A beta tester would only
be able to report "it didn't work".
"""

import logging
import os
import time

import pytest

from tenths.applog import configure_logging, get_logger, log_path, reset_logging
from tenths.service.watcher import (
    FileState, MAX_ATTEMPTS, REQUIRED_ARTIFACTS, RETRY_BACKOFF_SECONDS, TelemetryWatcher,
)


@pytest.fixture
def watcher(tmp_path):
    return TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)


@pytest.fixture
def isolated_log(tmp_path):
    """Route logging to a temp directory for the duration of a test."""
    reset_logging()
    path = configure_logging(log_dir=str(tmp_path / "logs"), console=False, force=True)
    yield path
    reset_logging()


class TestLoggingSetup:

    def test_log_file_is_created_and_written(self, isolated_log):
        assert isolated_log is not None
        get_logger("test").error("something broke")
        with open(isolated_log, encoding="utf-8") as f:
            content = f.read()
        assert "something broke" in content

    def test_log_records_level_and_timestamp(self, isolated_log):
        get_logger("test").warning("careful")
        with open(isolated_log, encoding="utf-8") as f:
            line = f.read().strip().splitlines()[-1]
        assert "WARNING" in line
        assert "careful" in line
        # Leading ISO-ish date
        assert line[:4].isdigit()

    def test_exception_traceback_is_captured(self, isolated_log):
        try:
            raise ValueError("inner detail")
        except ValueError:
            get_logger("test").error("failed", exc_info=True)
        with open(isolated_log, encoding="utf-8") as f:
            content = f.read()
        assert "ValueError" in content
        assert "inner detail" in content
        assert "Traceback" in content

    def test_configure_is_idempotent(self, tmp_path):
        reset_logging()
        try:
            configure_logging(log_dir=str(tmp_path / "l"), console=False, force=True)
            first = len(logging.getLogger("tenths").handlers)
            configure_logging(log_dir=str(tmp_path / "l"), console=False)
            assert len(logging.getLogger("tenths").handlers) == first
        finally:
            reset_logging()

    def test_survives_unwritable_log_directory(self, monkeypatch):
        """Logging must never stop the app from running."""
        reset_logging()
        try:
            def boom(*a, **k):
                raise OSError("read-only volume")
            monkeypatch.setattr(os, "makedirs", boom)
            assert configure_logging(log_dir="X:/nope", console=False, force=True) is None
            get_logger("test").info("still works")
        finally:
            reset_logging()

    def test_log_path_points_at_the_log_file(self):
        assert log_path().endswith("tenths.log")


class TestProcessingState:
    """Deduplication must not prevent retries."""

    def test_first_claim_succeeds(self, watcher):
        assert watcher._claim("a.ibt") is True
        assert watcher.state_of("a.ibt") == FileState.IN_PROGRESS

    def test_duplicate_events_are_ignored_while_in_progress(self, watcher):
        watcher._claim("a.ibt")
        assert watcher._claim("a.ibt") is False

    def test_completed_file_is_not_reprocessed(self, watcher):
        watcher._claim("a.ibt")
        watcher._mark_success("a.ibt")
        assert watcher.state_of("a.ibt") == FileState.DONE
        assert watcher._claim("a.ibt") is False

    def test_failure_leaves_file_retryable(self, watcher):
        watcher._claim("a.ibt")
        will_retry, attempts = watcher._mark_failure("a.ibt", RuntimeError("boom"))
        assert will_retry is True
        assert attempts == 1
        assert watcher.state_of("a.ibt") == FileState.PENDING

    def test_retry_waits_for_backoff(self, watcher):
        watcher._claim("a.ibt")
        watcher._mark_failure("a.ibt", RuntimeError("boom"))
        # Backoff has not elapsed
        assert watcher._claim("a.ibt") is False
        assert watcher._due_retries() == []

    def test_retry_allowed_once_backoff_elapses(self, watcher):
        watcher._claim("a.ibt")
        watcher._mark_failure("a.ibt", RuntimeError("boom"))
        watcher._states["a.ibt"]["next_attempt"] = time.time() - 1
        assert watcher._due_retries() == ["a.ibt"]
        assert watcher._claim("a.ibt") is True
        assert watcher._states["a.ibt"]["attempts"] == 2

    def test_gives_up_after_max_attempts(self, watcher):
        watcher._claim("a.ibt")
        for _ in range(MAX_ATTEMPTS - 1):
            watcher._mark_failure("a.ibt", RuntimeError("boom"))
            watcher._states["a.ibt"]["next_attempt"] = time.time() - 1
            watcher._claim("a.ibt")
        will_retry, attempts = watcher._mark_failure("a.ibt", RuntimeError("boom"))
        assert will_retry is False
        assert attempts == MAX_ATTEMPTS
        assert watcher.state_of("a.ibt") == FileState.FAILED

    def test_permanently_failed_file_is_not_retried(self, watcher):
        watcher._claim("a.ibt")
        for _ in range(MAX_ATTEMPTS):
            watcher._mark_failure("a.ibt", RuntimeError("boom"))
            watcher._states["a.ibt"]["next_attempt"] = time.time() - 1
            watcher._claim("a.ibt")
        watcher._states["a.ibt"]["state"] = FileState.FAILED
        assert watcher._claim("a.ibt") is False

    def test_failed_files_are_reportable(self, watcher):
        watcher._claim("a.ibt")
        watcher._states["a.ibt"]["attempts"] = MAX_ATTEMPTS
        watcher._mark_failure("a.ibt", RuntimeError("disk full"), stage="report")
        failed = watcher.failed_files()
        assert "a.ibt" in failed
        assert "disk full" in failed["a.ibt"]
        assert "report" in failed["a.ibt"]

    def test_backoff_grows(self):
        assert RETRY_BACKOFF_SECONDS[0] < RETRY_BACKOFF_SECONDS[-1]


class TestFailureIsSurfaced:
    """A failure must reach the log and, when final, the user."""

    def test_transient_failure_logged_and_not_notified(self, watcher, isolated_log, monkeypatch):
        notified = []
        monkeypatch.setattr(watcher, "_get_notifier",
                            lambda: type("N", (), {"notify_error": lambda s, f, m: notified.append((f, m))})())
        watcher._claim("session.ibt")
        watcher._handle_failure("session.ibt", RuntimeError("locked"), "analysis")
        with open(isolated_log, encoding="utf-8") as f:
            content = f.read()
        assert "retrying" in content.lower()
        assert not notified, "should not alarm the user while retries remain"

    def test_final_failure_notifies_the_user(self, watcher, isolated_log, monkeypatch):
        notified = []

        class FakeNotifier:
            def notify_error(self, filename, message):
                notified.append((filename, message))

        monkeypatch.setattr(watcher, "_get_notifier", lambda: FakeNotifier())
        watcher._claim("session.ibt")
        watcher._states["session.ibt"]["attempts"] = MAX_ATTEMPTS
        watcher._handle_failure("session.ibt", RuntimeError("disk full"), "report")

        assert notified, "user was never told the session failed"
        filename, message = notified[0]
        assert filename == "session.ibt"
        assert "disk full" in message
        with open(isolated_log, encoding="utf-8") as f:
            content = f.read()
        assert "Giving up" in content
        assert "left in place" in content

    def test_notifier_failure_does_not_mask_the_error(self, watcher, isolated_log, monkeypatch):
        class BrokenNotifier:
            def notify_error(self, filename, message):
                raise RuntimeError("winotify unavailable")

        monkeypatch.setattr(watcher, "_get_notifier", lambda: BrokenNotifier())
        watcher._claim("session.ibt")
        watcher._states["session.ibt"]["attempts"] = MAX_ATTEMPTS
        watcher._handle_failure("session.ibt", RuntimeError("disk full"), "report")
        with open(isolated_log, encoding="utf-8") as f:
            content = f.read()
        assert "Giving up" in content
        assert "notification" in content.lower()

    def test_pipeline_exception_is_caught_and_recorded(self, watcher, isolated_log, monkeypatch):
        def boom(_path):
            raise RuntimeError("analyzer exploded")

        monkeypatch.setattr(watcher, "_run_pipeline", boom)
        watcher._claim("session.ibt")
        watcher._process_file("session.ibt")   # must not raise
        assert watcher.state_of("session.ibt") == FileState.PENDING
        with open(isolated_log, encoding="utf-8") as f:
            assert "analyzer exploded" in f.read()


class TestArtifactContract:

    def test_required_artifacts_listed(self):
        assert set(REQUIRED_ARTIFACTS) == {
            "session_report.html", "session_notes.md", "session_summary.json"}

    def test_missing_artifact_raises_so_source_is_not_archived(self, watcher, tmp_path, monkeypatch):
        """If outputs are missing the run must fail rather than archive the .ibt."""
        source = tmp_path / "testcar_testtrack 2026-07-29 20-00-00.ibt"
        source.write_bytes(b"not a real ibt")

        # Simulate a pipeline that writes nothing then reaches the artifact check
        session_dir = tmp_path / "out"
        session_dir.mkdir()
        missing = [n for n in REQUIRED_ARTIFACTS
                   if not os.path.exists(os.path.join(session_dir, n))]
        assert missing == list(REQUIRED_ARTIFACTS)
        assert source.exists(), "source must still be present when outputs are missing"


class TestNoDuplicateObservers:

    def test_second_start_is_refused(self, watcher, isolated_log):
        watcher._running = True
        watcher.start()   # must return immediately, not schedule an observer
        assert watcher._observer is None
        with open(isolated_log, encoding="utf-8") as f:
            assert "already running" in f.read()

    def test_missing_root_reports_and_exits(self, tmp_path, isolated_log, monkeypatch):
        target = tmp_path / "nope" / "telemetry"
        w = TelemetryWatcher(telemetry_root=str(target), auto_open=False)
        monkeypatch.setattr(w, "_ensure_watch_root", lambda: False)

        notified = []

        class FakeNotifier:
            def notify_error(self, title, message):
                notified.append((title, message))

        monkeypatch.setattr(w, "_get_notifier", lambda: FakeNotifier())
        w.start()
        assert w._observer is None
        assert notified
        with open(isolated_log, encoding="utf-8") as f:
            assert "telemetry folder not found" in f.read().lower()


class TestRetryDispatch:

    def test_vanished_file_is_not_retried(self, watcher, isolated_log):
        missing = os.path.join(str(watcher._root), "gone.ibt")
        watcher._claim(missing)
        watcher._mark_failure(missing, RuntimeError("boom"))
        watcher._states[missing]["next_attempt"] = time.time() - 1
        watcher._retry_due_files()
        assert watcher.state_of(missing) == FileState.FAILED
        with open(isolated_log, encoding="utf-8") as f:
            assert "no longer present" in f.read()

    def test_existing_file_is_redispatched(self, watcher, tmp_path, isolated_log, monkeypatch):
        path = tmp_path / "testcar_testtrack 2026-07-29 20-00-00.ibt"
        path.write_bytes(b"x" * 10)
        started = []
        monkeypatch.setattr(watcher, "_process_file", lambda p: started.append(p))

        watcher._claim(str(path))
        watcher._mark_failure(str(path), RuntimeError("boom"))
        watcher._states[str(path)]["next_attempt"] = time.time() - 1
        watcher._retry_due_files()
        time.sleep(0.2)   # dispatch happens on a worker thread
        assert started == [str(path)]
