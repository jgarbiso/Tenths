"""
Tests for distribution-readiness fixes (docs/DISTRIBUTION_READINESS.md).

Covers:
- D1: race result matching uses caller-provided cust_id (no hardcoded ID)
- D3: incidents module exposes a callable main()
- D4: PyYAML declared as a dependency
- D8: malformed/short result files degrade gracefully
"""

import os
import csv
import tempfile

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write_csv(rows):
    """Write CSV lines to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix='.csv')
    os.close(fd)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(rows))
    return path


# A minimal valid iRacing-style CSV: metadata header + values, blank, results header + rows
_VALID_CSV = [
    "Series,Track,Strength of Field,Start Time,Season Year,Season Quarter,Race Week",
    "Test Series,Test Track,1500,2026-01-01,2026,1,1",
    "",
    "Fin Pos,Name,Car,Car Class,Start Pos,Laps Comp,Inc,Interval,Average Lap Time,Fastest Lap Time,Fast Lap#,Cust ID,Old iRating,New iRating,Old License Level,Old License Sub-Level,New License Level,New License Sub-Level,Out",
    "1,Alice,Ferrari,GT3,1,10,0,0,90.5,89.9,5,111,2000,2020,20,400,20,410,Running",
    "2,Bob,BMW,GT3,2,10,2,1.2,91.0,90.5,6,222,1800,1790,18,300,18,295,Running",
]


class TestD1_NoHardcodedCustId:
    """D1: race result matching must use the caller-provided cust_id."""

    def test_my_result_matched_by_cust_id(self):
        from tenths.results import parse_result
        path = _write_csv(_VALID_CSV)
        try:
            data = parse_result(path, my_cust_id=222)
            assert data['my_result'] is not None
            assert data['my_result']['name'] == 'Bob'
            assert data['my_result']['finish_pos'] == 2
        finally:
            os.remove(path)

    def test_different_cust_id_matches_different_driver(self):
        """A different user's cust_id matches their own row — proves no hardcoding."""
        from tenths.results import parse_result
        path = _write_csv(_VALID_CSV)
        try:
            data = parse_result(path, my_cust_id=111)
            assert data['my_result']['name'] == 'Alice'
        finally:
            os.remove(path)

    def test_no_cust_id_means_no_my_result(self):
        """Without a cust_id, my_result stays None (no accidental match)."""
        from tenths.results import parse_result
        path = _write_csv(_VALID_CSV)
        try:
            data = parse_result(path, my_cust_id=None)
            assert data['my_result'] is None
        finally:
            os.remove(path)

    def test_unknown_cust_id_no_match(self):
        """A cust_id not in the field returns no my_result (doesn't crash)."""
        from tenths.results import parse_result
        path = _write_csv(_VALID_CSV)
        try:
            data = parse_result(path, my_cust_id=999999)
            assert data['my_result'] is None
        finally:
            os.remove(path)

    def test_no_hardcoded_id_in_source(self):
        """The old hardcoded customer ID must not exist in results.py."""
        results_py = os.path.join(PROJECT_ROOT, "tenths", "results.py")
        with open(results_py, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "MY_CUST_ID" not in content
        assert "1434150" not in content  # owner's real ID must not be hardcoded


class TestD8_MalformedResultFiles:
    """D8: malformed/short result files degrade gracefully, not crash."""

    def test_empty_csv_returns_none(self):
        from tenths.results import parse_result
        path = _write_csv([])
        try:
            assert parse_result(path, my_cust_id=111) is None
        finally:
            os.remove(path)

    def test_single_line_csv_returns_none(self):
        from tenths.results import parse_result
        path = _write_csv(["just one line"])
        try:
            assert parse_result(path, my_cust_id=111) is None
        finally:
            os.remove(path)

    def test_metadata_only_no_results(self):
        """Metadata present but no result rows degrades gracefully (no crash)."""
        from tenths.results import parse_result
        path = _write_csv([_VALID_CSV[0], _VALID_CSV[1], "", _VALID_CSV[3]])
        try:
            result = parse_result(path, my_cust_id=111)
            # Either None or a dict with no entries/my_result — both are graceful
            if result is not None:
                assert result['entries'] == 0
                assert result['my_result'] is None
        finally:
            os.remove(path)

    def test_nonexistent_file(self):
        from tenths.results import parse_result
        assert parse_result("/no/such/file.csv", my_cust_id=111) is None


class TestD3_IncidentsMain:
    """D3: the incidents module must expose a callable main() so the CLI works."""

    def test_incidents_has_main(self):
        from tenths.incidents import main
        assert callable(main)

    def test_incidents_has_analyze_function(self):
        from tenths.incidents import analyze_incidents
        assert callable(analyze_incidents)

    def test_analyze_incidents_missing_file_graceful(self, capsys):
        """A missing file prints a message and returns without raising."""
        from tenths.incidents import analyze_incidents
        analyze_incidents("/no/such/file.ibt", [2])
        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_cli_imports_incident_main(self):
        """The CLI's import of incidents.main must succeed (regression guard)."""
        import importlib
        mod = importlib.import_module("tenths.incidents")
        assert hasattr(mod, "main")


class TestD4_PyYamlDependency:
    """D4: PyYAML must be declared as a dependency (analyzer imports yaml)."""

    def test_pyyaml_in_pyproject(self):
        import tomllib
        pyproject = os.path.join(PROJECT_ROOT, "pyproject.toml")
        with open(pyproject, 'rb') as f:
            data = tomllib.load(f)
        deps = data['project']['dependencies']
        assert any('yaml' in d.lower() for d in deps), "PyYAML must be a declared dependency"

    def test_yaml_importable(self):
        import yaml
        assert yaml is not None


class TestD2_WatcherFolderGuard:
    """D2: watcher must not crash when the telemetry folder is missing.

    Updated 2026-07-29: it must also not invent a telemetry folder at a path
    that was resolved wrongly. Creating one made a misresolved Documents folder
    (OneDrive redirection) look like a healthy install that never produced a
    report. The iRacing folder is the signal for whether the location is right.
    """

    def test_creates_telemetry_folder_when_iracing_folder_exists(self, tmp_path):
        """Right location, telemetry subfolder simply not created yet."""
        from tenths.service.watcher import TelemetryWatcher
        iracing = tmp_path / "iRacing"
        iracing.mkdir()
        missing = str(iracing / "telemetry")
        w = TelemetryWatcher(telemetry_root=missing, auto_open=False)
        assert w._ensure_watch_root() is True
        assert os.path.isdir(missing)

    def test_refuses_when_iracing_folder_is_absent(self, tmp_path):
        """Wrong location — must report rather than create a decoy folder."""
        from tenths.service.watcher import TelemetryWatcher
        missing = str(tmp_path / "does_not_exist_yet" / "telemetry")
        w = TelemetryWatcher(telemetry_root=missing, auto_open=False)
        assert w._ensure_watch_root() is False
        assert not os.path.exists(missing), (
            "a telemetry folder was created at an unverified location, which "
            "hides the failure instead of reporting it")

    def test_ensure_watch_root_existing(self, tmp_path):
        from tenths.service.watcher import TelemetryWatcher
        w = TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)
        assert w._ensure_watch_root() is True


class TestConsoleUtf8Safe:
    """Console output must not crash on Unicode chars (→, ✓) on cp1252 consoles."""

    def test_configure_console_callable(self):
        from tenths.config import configure_console
        assert callable(configure_console)

    def test_configure_console_no_error(self):
        """Calling it must never raise, regardless of stream state."""
        from tenths.config import configure_console
        configure_console()  # should not raise

    def test_configure_console_handles_none_stdout(self, monkeypatch):
        """Guards the frozen/no-console case where stdout is None."""
        import sys
        from tenths.config import configure_console
        monkeypatch.setattr(sys, 'stdout', None)
        monkeypatch.setattr(sys, 'stderr', None)
        configure_console()  # must not raise even with None streams
