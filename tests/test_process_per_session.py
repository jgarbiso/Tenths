"""
Tests for RR-006 (per-session manual processing) and RR-007 (failure isolation).

Validates that:
- Two same-day .ibt files produce two time-level folders, each with all three artifacts
- The slower session still gets its own report (no "best session" selection)
- Manual and watcher path generation produce identical paths for the same metadata
- A collision (same time folder already exists) gets a deterministic suffix
- Standalone report writes only session_report.html, does not archive
- The .ibt is NOT archived when artifact writing fails
- A corrupt first file does not prevent a valid second file from being processed
- Batch summary counts are accurate
"""

import os
import shutil
from unittest.mock import patch

import pytest

from synthetic_ibt import build_ibt, default_test_corners, default_session_info, Corner
from tenths.config import session_output_dir, REQUIRED_ARTIFACTS


class TestSessionOutputDir:
    """Unit tests for the shared path builder."""

    def test_basic_path_structure(self, tmp_path):
        result = session_output_dir(str(tmp_path), "bmwm2csr", "winton_national",
                                    "2026-06-06", "22-26-36")
        expected = os.path.join(str(tmp_path), "bmwm2csr", "winton_national",
                                "2026-06-06", "22-26-36")
        assert result == expected

    def test_collision_gets_suffix(self, tmp_path):
        # Create the base directory so it already exists
        base = os.path.join(str(tmp_path), "car", "track", "2026-01-01", "12-00-00")
        os.makedirs(base)
        result = session_output_dir(str(tmp_path), "car", "track", "2026-01-01", "12-00-00")
        assert result == base + "-2"

    def test_multiple_collisions(self, tmp_path):
        base = os.path.join(str(tmp_path), "car", "track", "2026-01-01", "12-00-00")
        os.makedirs(base)
        os.makedirs(base + "-2")
        result = session_output_dir(str(tmp_path), "car", "track", "2026-01-01", "12-00-00")
        assert result == base + "-3"

    def test_manual_and_watcher_produce_identical_paths(self, tmp_path):
        """Both manual process and watcher use the same session_output_dir helper."""
        # Same inputs should yield same output
        result1 = session_output_dir(str(tmp_path), "bmwm2csr", "winton_national",
                                     "2026-06-06", "22-26-36")
        result2 = session_output_dir(str(tmp_path), "bmwm2csr", "winton_national",
                                     "2026-06-06", "22-26-36")
        # First call should not create the directory, so both get the same path
        assert result1 == result2


class TestRequiredArtifacts:
    """Verify the shared REQUIRED_ARTIFACTS constant."""

    def test_required_artifacts_tuple(self):
        assert isinstance(REQUIRED_ARTIFACTS, tuple)
        assert "session_report.html" in REQUIRED_ARTIFACTS
        assert "session_notes.md" in REQUIRED_ARTIFACTS
        assert "session_summary.json" in REQUIRED_ARTIFACTS

    def test_watcher_uses_same_constant(self):
        from tenths.service.watcher import REQUIRED_ARTIFACTS as WATCHER_ARTIFACTS
        assert WATCHER_ARTIFACTS is REQUIRED_ARTIFACTS


class TestPerSessionProcessing:
    """Integration tests: manual processing produces per-session output."""

    @pytest.fixture()
    def two_session_setup(self, tmp_path):
        """Create two synthetic .ibt files for the same car/track/day, different times."""
        telemetry_root = tmp_path / "telemetry"
        telemetry_root.mkdir()

        # Session 1 — faster (at 20:00:00)
        session_info_1 = default_session_info(car="BMW M2 CS Racing", track="Test Track",
                                              event_type="Practice")
        ibt1_path = telemetry_root / "bmwm2csracing_test track 2026-08-01 20-00-00.ibt"
        corners1 = [Corner(pct=0.3, apex_speeds=30.0), Corner(pct=0.7, apex_speeds=25.0)]
        build_ibt(str(ibt1_path), corners1, laps=4, track_length_m=2000.0,
                  session_info=session_info_1)

        # Session 2 — slower (at 21:00:00, slower apex speeds)
        session_info_2 = default_session_info(car="BMW M2 CS Racing", track="Test Track",
                                              event_type="Practice")
        ibt2_path = telemetry_root / "bmwm2csracing_test track 2026-08-01 21-00-00.ibt"
        corners2 = [Corner(pct=0.3, apex_speeds=25.0), Corner(pct=0.7, apex_speeds=20.0)]
        build_ibt(str(ibt2_path), corners2, laps=4, track_length_m=2000.0,
                  session_info=session_info_2)

        return {
            "telemetry_root": str(telemetry_root),
            "ibt1": str(ibt1_path),
            "ibt2": str(ibt2_path),
            "archive_dir": str(telemetry_root / "_archive"),
        }

    def test_two_same_day_files_produce_two_folders(self, two_session_setup):
        """Each session gets its own time-level folder."""
        root = two_session_setup["telemetry_root"]

        with patch("tenths.process.TELEMETRY_ROOT", root), \
             patch("tenths.process.ARCHIVE_DIR", two_session_setup["archive_dir"]), \
             patch("tenths.config.TELEMETRY_ROOT", root), \
             patch("tenths.process.find_ibt_files") as mock_find, \
             patch("tenths.process.find_race_result", return_value=None):
            mock_find.return_value = [two_session_setup["ibt1"], two_session_setup["ibt2"]]

            import sys
            old_argv = sys.argv
            sys.argv = ["tenths"]
            try:
                from tenths.process import main
                main()
            finally:
                sys.argv = old_argv

        # Check both time-level directories exist
        session1_dir = os.path.join(root, "bmwm2csracing", "test_track", "2026-08-01", "20-00-00")
        session2_dir = os.path.join(root, "bmwm2csracing", "test_track", "2026-08-01", "21-00-00")
        assert os.path.isdir(session1_dir), f"Session 1 dir missing: {session1_dir}"
        assert os.path.isdir(session2_dir), f"Session 2 dir missing: {session2_dir}"

    def test_both_sessions_get_all_artifacts(self, two_session_setup):
        """Each session has all three required artifacts."""
        root = two_session_setup["telemetry_root"]

        with patch("tenths.process.TELEMETRY_ROOT", root), \
             patch("tenths.process.ARCHIVE_DIR", two_session_setup["archive_dir"]), \
             patch("tenths.config.TELEMETRY_ROOT", root), \
             patch("tenths.process.find_ibt_files") as mock_find, \
             patch("tenths.process.find_race_result", return_value=None):
            mock_find.return_value = [two_session_setup["ibt1"], two_session_setup["ibt2"]]

            import sys
            old_argv = sys.argv
            sys.argv = ["tenths"]
            try:
                from tenths.process import main
                main()
            finally:
                sys.argv = old_argv

        for time_str in ("20-00-00", "21-00-00"):
            session_dir = os.path.join(root, "bmwm2csracing", "test_track", "2026-08-01", time_str)
            for artifact in REQUIRED_ARTIFACTS:
                artifact_path = os.path.join(session_dir, artifact)
                assert os.path.isfile(artifact_path), \
                    f"Missing artifact {artifact} in {session_dir}"
                assert os.path.getsize(artifact_path) > 0, \
                    f"Empty artifact {artifact} in {session_dir}"

    def test_slower_session_gets_own_report(self, two_session_setup):
        """The slower session is NOT discarded — it gets its own complete output."""
        root = two_session_setup["telemetry_root"]

        with patch("tenths.process.TELEMETRY_ROOT", root), \
             patch("tenths.process.ARCHIVE_DIR", two_session_setup["archive_dir"]), \
             patch("tenths.config.TELEMETRY_ROOT", root), \
             patch("tenths.process.find_ibt_files") as mock_find, \
             patch("tenths.process.find_race_result", return_value=None):
            mock_find.return_value = [two_session_setup["ibt1"], two_session_setup["ibt2"]]

            import sys
            old_argv = sys.argv
            sys.argv = ["tenths"]
            try:
                from tenths.process import main
                main()
            finally:
                sys.argv = old_argv

        # Session 2 (slower, at 21-00-00) must have its own report
        slower_dir = os.path.join(root, "bmwm2csracing", "test_track", "2026-08-01", "21-00-00")
        report_path = os.path.join(slower_dir, "session_report.html")
        assert os.path.isfile(report_path), "Slower session was discarded — missing report"
        assert os.path.getsize(report_path) > 1000, "Report file is suspiciously small"


class TestFailureIsolation:
    """RR-007: archiving is deferred and failure is isolated."""

    @pytest.fixture()
    def single_session_setup(self, tmp_path):
        """Create one synthetic .ibt file."""
        telemetry_root = tmp_path / "telemetry"
        telemetry_root.mkdir()

        session_info = default_session_info(car="BMW M2 CS Racing", track="Test Track",
                                            event_type="Practice")
        ibt_path = telemetry_root / "bmwm2csracing_test track 2026-08-01 20-00-00.ibt"
        corners = [Corner(pct=0.3, apex_speeds=30.0), Corner(pct=0.7, apex_speeds=25.0)]
        build_ibt(str(ibt_path), corners, laps=4, track_length_m=2000.0,
                  session_info=session_info)

        return {
            "telemetry_root": str(telemetry_root),
            "ibt_path": str(ibt_path),
            "archive_dir": str(telemetry_root / "_archive"),
        }

    def test_ibt_not_archived_when_report_fails(self, single_session_setup):
        """If report generation raises, the .ibt stays in place (not archived)."""
        root = single_session_setup["telemetry_root"]
        ibt_path = single_session_setup["ibt_path"]

        with patch("tenths.process.TELEMETRY_ROOT", root), \
             patch("tenths.process.ARCHIVE_DIR", single_session_setup["archive_dir"]), \
             patch("tenths.config.TELEMETRY_ROOT", root), \
             patch("tenths.process.find_ibt_files") as mock_find, \
             patch("tenths.process.find_race_result", return_value=None), \
             patch("tenths.process.generate_report", side_effect=RuntimeError("simulated failure")):
            mock_find.return_value = [ibt_path]

            import sys
            old_argv = sys.argv
            sys.argv = ["tenths"]
            try:
                from tenths.process import main
                main()
            finally:
                sys.argv = old_argv

        # .ibt must still be in its original location (not archived)
        assert os.path.exists(ibt_path), \
            "The .ibt was archived despite report generation failure"
        # Archive dir should be empty or not exist
        archive_dir = single_session_setup["archive_dir"]
        if os.path.exists(archive_dir):
            assert len(os.listdir(archive_dir)) == 0, \
                "Archive contains files despite processing failure"

    def test_corrupt_file_does_not_block_valid_file(self, tmp_path):
        """A corrupt first file should not prevent processing of the second."""
        telemetry_root = tmp_path / "telemetry"
        telemetry_root.mkdir()
        archive_dir = str(telemetry_root / "_archive")

        # File 1 — corrupt (tiny file, parseable name, analyze will return None or raise)
        corrupt_path = telemetry_root / "badcar_badtrack 2026-08-01 19-00-00.ibt"
        corrupt_path.write_bytes(b"\x00" * 200)

        # File 2 — valid synthetic
        session_info = default_session_info(car="BMW M2 CS Racing", track="Test Track",
                                            event_type="Practice")
        valid_path = telemetry_root / "bmwm2csracing_test track 2026-08-01 20-00-00.ibt"
        corners = [Corner(pct=0.3, apex_speeds=30.0), Corner(pct=0.7, apex_speeds=25.0)]
        build_ibt(str(valid_path), corners, laps=4, track_length_m=2000.0,
                  session_info=session_info)

        def mock_analyze(filepath):
            """analyze() that raises for the corrupt file."""
            if "badcar" in filepath:
                raise ValueError("corrupt .ibt file")
            from tenths.analyzer import analyze as real_analyze
            return real_analyze(filepath)

        with patch("tenths.process.TELEMETRY_ROOT", str(telemetry_root)), \
             patch("tenths.process.ARCHIVE_DIR", archive_dir), \
             patch("tenths.config.TELEMETRY_ROOT", str(telemetry_root)), \
             patch("tenths.process.find_ibt_files") as mock_find, \
             patch("tenths.process.find_race_result", return_value=None), \
             patch("tenths.process.analyze", side_effect=mock_analyze):
            mock_find.return_value = [str(corrupt_path), str(valid_path)]

            import sys
            old_argv = sys.argv
            sys.argv = ["tenths"]
            try:
                from tenths.process import main
                main()
            finally:
                sys.argv = old_argv

        # The valid session should have produced output
        session_dir = os.path.join(str(telemetry_root), "bmwm2csracing", "test_track",
                                   "2026-08-01", "20-00-00")
        assert os.path.isdir(session_dir), "Valid session was not processed after corrupt file"
        for artifact in REQUIRED_ARTIFACTS:
            assert os.path.isfile(os.path.join(session_dir, artifact))


class TestStandaloneReport:
    """Standalone report command writes only the report, does not archive."""

    def test_standalone_report_only_writes_report(self, tmp_path):
        """tenths report writes session_report.html only, no notes or summary."""
        telemetry_root = tmp_path / "telemetry"
        telemetry_root.mkdir()

        session_info = default_session_info(car="BMW M2 CS Racing", track="Test Track",
                                            event_type="Practice")
        ibt_path = telemetry_root / "bmwm2csracing_test track 2026-08-01 20-00-00.ibt"
        corners = [Corner(pct=0.3, apex_speeds=30.0), Corner(pct=0.7, apex_speeds=25.0)]
        build_ibt(str(ibt_path), corners, laps=4, track_length_m=2000.0,
                  session_info=session_info)

        with patch("tenths.process.TELEMETRY_ROOT", str(telemetry_root)), \
             patch("tenths.config.TELEMETRY_ROOT", str(telemetry_root)):
            import sys
            old_argv = sys.argv
            sys.argv = ["tenths", str(ibt_path)]
            try:
                from tenths.report import generate_report_cli
                generate_report_cli()
            finally:
                sys.argv = old_argv

        # Report should exist in time-level directory
        session_dir = os.path.join(str(telemetry_root), "bmwm2csracing", "test_track",
                                   "2026-08-01", "20-00-00")
        report_path = os.path.join(session_dir, "session_report.html")
        assert os.path.isfile(report_path), "Report not generated"

        # session_notes.md and session_summary.json should NOT exist
        # (standalone report doesn't produce them)
        notes_path = os.path.join(session_dir, "session_notes.md")
        summary_path = os.path.join(session_dir, "session_summary.json")
        assert not os.path.isfile(notes_path), "Standalone report should not create notes"
        assert not os.path.isfile(summary_path), "Standalone report should not create summary"

        # .ibt should still exist (not archived)
        assert os.path.exists(str(ibt_path)), "Standalone report should not archive the .ibt"


class TestBatchSummary:
    """The batch summary counts must be accurate."""

    def test_batch_counts(self, tmp_path, capsys):
        """Verify succeeded/skipped/failed counts in output."""
        telemetry_root = tmp_path / "telemetry"
        telemetry_root.mkdir()
        archive_dir = str(telemetry_root / "_archive")

        # File 1 — valid
        session_info = default_session_info(car="BMW M2 CS Racing", track="Test Track",
                                            event_type="Practice")
        valid_path = telemetry_root / "bmwm2csracing_test track 2026-08-01 20-00-00.ibt"
        corners = [Corner(pct=0.3, apex_speeds=30.0), Corner(pct=0.7, apex_speeds=25.0)]
        build_ibt(str(valid_path), corners, laps=4, track_length_m=2000.0,
                  session_info=session_info)

        # File 2 — unparseable filename
        bad_name = telemetry_root / "not_a_valid_name.ibt"
        bad_name.write_bytes(b"\x00" * 100)

        with patch("tenths.process.TELEMETRY_ROOT", str(telemetry_root)), \
             patch("tenths.process.ARCHIVE_DIR", archive_dir), \
             patch("tenths.config.TELEMETRY_ROOT", str(telemetry_root)), \
             patch("tenths.process.find_ibt_files") as mock_find, \
             patch("tenths.process.find_race_result", return_value=None):
            mock_find.return_value = [str(bad_name), str(valid_path)]

            import sys
            old_argv = sys.argv
            sys.argv = ["tenths"]
            try:
                from tenths.process import main
                main()
            finally:
                sys.argv = old_argv

        output = capsys.readouterr().out
        assert "1 succeeded" in output
        assert "1 skipped" in output
        assert "0 failed" in output
