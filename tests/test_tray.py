"""
Tests for system tray application logic.

Registry access is exercised against an in-memory fake (see conftest) so a test
run can never create, change or delete the user's real "Start with Windows"
setting. Report lookup runs against temporary directories rather than whatever
happens to exist on the developer's machine.
"""

import os
import time

import pytest
from unittest.mock import MagicMock

from tenths.service.tray import TenthsTray, ICON_PATH, STARTUP_REG_KEY, STARTUP_REG_PATH


class TestTrayInit:
    """Test tray app initialization."""

    def test_icon_file_exists(self):
        """The icon file should exist at the expected path."""
        assert os.path.exists(ICON_PATH), f"Icon not found at {ICON_PATH}"

    def test_icon_loads(self):
        """Icon should load without error."""
        from PIL import Image
        img = Image.open(ICON_PATH)
        assert img.size[0] > 0
        assert img.size[1] > 0

    def test_tray_creates_without_error(self):
        """TenthsTray should instantiate without error."""
        tray = TenthsTray()
        assert tray._paused is False
        assert tray._watcher is None
        assert tray._last_report is None

    def test_open_index_exists_in_menu(self):
        """Browse Sessions must appear in the tray menu."""
        tray = TenthsTray()
        assert hasattr(tray, '_open_index')
        assert callable(tray._open_index)


class TestTrayFindReport:
    """Test finding the latest report against a controlled directory tree."""

    def _write_report(self, root, rel_path, mtime):
        # Build with os.path.join so the expected value uses native separators,
        # matching what glob returns.
        path = os.path.join(root, *rel_path.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write("<html></html>")
        os.utime(path, (mtime, mtime))
        return path

    def test_returns_most_recently_modified_report(self, tmp_path, monkeypatch):
        """Picks the newest report, not simply the first one found."""
        from tenths.service import tray as tray_mod
        root = str(tmp_path)
        now = time.time()
        self._write_report(root, "carA/track1/2026-07-01/10-00-00/session_report.html", now - 5000)
        newest = self._write_report(
            root, "carB/track2/2026-07-29/22-09-18/session_report.html", now)
        self._write_report(root, "carC/track3/2026-07-15/12-00-00/session_report.html", now - 200)

        monkeypatch.setattr(tray_mod, "TELEMETRY_ROOT", root)
        assert TenthsTray()._find_latest_report() == newest

    def test_finds_nested_per_session_reports(self, tmp_path, monkeypatch):
        """Recursive search must reach car/track/date/time folders."""
        from tenths.service import tray as tray_mod
        root = str(tmp_path)
        expected = self._write_report(
            root, "ferrari296gt3/coronado/2026-07-29/22-09-18/session_report.html", time.time())
        monkeypatch.setattr(tray_mod, "TELEMETRY_ROOT", root)
        assert TenthsTray()._find_latest_report() == expected

    def test_returns_none_when_no_reports_exist(self, tmp_path, monkeypatch):
        """Empty telemetry tree yields None rather than raising."""
        from tenths.service import tray as tray_mod
        monkeypatch.setattr(tray_mod, "TELEMETRY_ROOT", str(tmp_path))
        assert TenthsTray()._find_latest_report() is None

    def test_ignores_non_report_files(self, tmp_path, monkeypatch):
        """Only session_report.html counts."""
        from tenths.service import tray as tray_mod
        root = str(tmp_path)
        os.makedirs(os.path.join(root, "carA", "track1"), exist_ok=True)
        for name in ("session_summary.json", "session_notes.md", "index.html"):
            with open(os.path.join(root, "carA", "track1", name), 'w', encoding='utf-8') as f:
                f.write("x")
        monkeypatch.setattr(tray_mod, "TELEMETRY_ROOT", root)
        assert TenthsTray()._find_latest_report() is None


class TestTrayStartup:
    """Windows startup registration, against an in-memory registry."""

    def test_not_registered_when_value_absent(self, fake_registry):
        assert TenthsTray()._is_startup_registered() is False

    def test_registered_when_value_present(self, fake_registry):
        fake_registry.values[STARTUP_REG_KEY] = r'"C:\some\Tenths.exe"'
        assert TenthsTray()._is_startup_registered() is True

    def test_register_writes_startup_value(self, fake_registry):
        TenthsTray()._register_startup()
        assert STARTUP_REG_KEY in fake_registry.values
        assert TenthsTray()._is_startup_registered() is True

    def test_registered_command_is_quoted_and_launches_tray(self, fake_registry):
        """The command must be quoted (spaces in paths) and start the tray."""
        TenthsTray()._register_startup()
        cmd = fake_registry.values[STARTUP_REG_KEY]
        assert cmd.startswith('"'), f"executable not quoted: {cmd}"
        assert cmd.count('"') >= 2
        assert "tenths.cli" in cmd and "tray" in cmd

    def test_register_unregister_round_trip(self, fake_registry):
        tray = TenthsTray()
        tray._register_startup()
        assert tray._is_startup_registered() is True
        tray._unregister_startup()
        assert tray._is_startup_registered() is False
        assert STARTUP_REG_KEY not in fake_registry.values

    def test_unregister_when_absent_is_silent(self, fake_registry):
        """Removing a value that was never set must not raise."""
        TenthsTray()._unregister_startup()
        assert STARTUP_REG_KEY not in fake_registry.values

    def test_register_failure_is_handled(self, fake_registry):
        """A denied write must not propagate out of the tray menu handler."""
        fake_registry.fail_on_set = True
        TenthsTray()._register_startup()  # must not raise
        assert STARTUP_REG_KEY not in fake_registry.values

    def test_is_registered_survives_open_failure(self, fake_registry):
        fake_registry.fail_on_open = True
        assert TenthsTray()._is_startup_registered() is False

    def test_registry_handles_are_closed(self, fake_registry):
        """Every opened key must be closed — no handle leaks."""
        tray = TenthsTray()
        tray._register_startup()
        tray._is_startup_registered()
        tray._unregister_startup()
        assert fake_registry.close_count == fake_registry.open_count

    def test_uses_the_run_key_path(self):
        """Guard the registry location so it cannot silently move."""
        assert STARTUP_REG_PATH == r"Software\Microsoft\Windows\CurrentVersion\Run"
        assert STARTUP_REG_KEY == "Tenths"

    def test_toggle_registers_then_unregisters(self, fake_registry):
        tray = TenthsTray()
        tray._toggle_startup()
        assert tray._is_startup_registered() is True
        tray._toggle_startup()
        assert tray._is_startup_registered() is False


class TestRegistryIsolation:
    """The guard itself must be working."""

    def test_tray_module_uses_the_fake(self, fake_registry):
        from tenths.service import tray as tray_mod
        assert tray_mod.winreg is fake_registry

    def test_real_winreg_not_used_by_default(self):
        """Even without requesting the fixture, winreg must be substituted."""
        from tenths.service import tray as tray_mod
        assert tray_mod.winreg.__class__.__name__ == "FakeRegistry"


class TestTrayPause:
    """Test pause/resume functionality."""

    def test_toggle_pause_state(self):
        """Pausing should toggle the _paused flag and stop the watcher."""
        tray = TenthsTray()
        tray._icon = MagicMock()
        tray._watcher = MagicMock()

        assert tray._paused is False
        tray._toggle_pause()
        assert tray._paused is True
        tray._watcher.stop.assert_called_once()

    def test_pause_updates_icon_title(self):
        tray = TenthsTray()
        tray._icon = MagicMock()
        tray._watcher = MagicMock()
        tray._toggle_pause()
        assert "Paused" in tray._icon.title


class TestFrozenEntryPointDispatch:
    """The packaged build ships one exe, so tray.main() is also the CLI entry.

    BETA_TESTING.md tells testers to run `Tenths.exe config`. Before this
    dispatch existed the exe ignored its arguments and silently started the tray,
    so the documented command was simply untrue.
    """

    def test_no_args_starts_tray_not_cli(self, monkeypatch):
        import tenths.service.tray as tray_mod

        started = []
        monkeypatch.setattr(tray_mod, 'TenthsTray',
                            lambda: MagicMock(run=lambda: started.append('tray')))
        monkeypatch.setattr('sys.argv', ['Tenths.exe'])

        tray_mod.main()

        assert started == ['tray'], "bare invocation must start the tray"

    def test_args_are_forwarded_to_cli(self, monkeypatch):
        import tenths.service.tray as tray_mod
        import tenths.cli as cli_mod

        seen = []
        monkeypatch.setattr(cli_mod, 'main', lambda argv=None: seen.append(argv))
        monkeypatch.setattr(tray_mod, 'TenthsTray',
                            lambda: pytest.fail("tray must not start when args are given"))

        tray_mod.main(['config'])

        assert seen == [['config']], "arguments must reach the CLI unchanged"

    def test_args_read_from_sys_argv_when_not_passed(self, monkeypatch):
        """This is the real frozen path: Windows supplies argv, nothing passes it."""
        import tenths.service.tray as tray_mod
        import tenths.cli as cli_mod

        seen = []
        monkeypatch.setattr(cli_mod, 'main', lambda argv=None: seen.append(argv))
        monkeypatch.setattr(tray_mod, 'TenthsTray',
                            lambda: pytest.fail("tray must not start when args are given"))
        monkeypatch.setattr('sys.argv',
                            ['Tenths.exe', 'config', '--telemetry-root', 'D:\\tel'])

        tray_mod.main()

        assert seen == [['config', '--telemetry-root', 'D:\\tel']]

    def test_cli_tray_command_does_not_recurse(self, monkeypatch):
        """`tenths tray` must reach the tray, not bounce back into the CLI.

        tray.main() forwards arguments to cli.main(); if the CLI's own `tray`
        branch forwarded its remaining argv, the two would call each other until
        the stack ran out.
        """
        import tenths.cli as cli_mod
        import tenths.service.tray as tray_mod

        started = []
        monkeypatch.setattr(tray_mod, 'TenthsTray',
                            lambda: MagicMock(run=lambda: started.append('tray')))
        monkeypatch.setattr('sys.argv', ['tenths', 'tray'])

        cli_mod.main()

        assert started == ['tray']

    def test_attach_parent_console_is_safe_when_not_frozen(self, monkeypatch):
        """Must never raise: it runs before any error handling is in place."""
        from tenths.config import attach_parent_console

        monkeypatch.delattr('sys.frozen', raising=False)
        result = attach_parent_console()

        assert isinstance(result, bool)
