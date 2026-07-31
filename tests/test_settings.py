"""
RR-012: user-configurable telemetry location and one-time setup guidance.

An installed user will never set an environment variable, so an unusual iRacing
layout needs a settings file. And a user whose telemetry logging has never been
enabled must be told, rather than watching a healthy-looking tray icon forever.
"""

import json
import os

import pytest

import tenths.config as cfg


@pytest.fixture
def settings_file(tmp_path):
    return str(tmp_path / "settings.json")


class TestSettingsFile:

    def test_missing_file_returns_empty(self, settings_file):
        assert cfg.load_settings(settings_file) == {}

    def test_round_trip(self, settings_file):
        cfg.save_settings({"telemetry_root": r"D:\iracing\telemetry"}, settings_file)
        assert cfg.load_settings(settings_file)["telemetry_root"] == r"D:\iracing\telemetry"

    def test_save_merges_rather_than_replaces(self, settings_file):
        cfg.save_settings({"telemetry_root": "D:\\a"}, settings_file)
        cfg.save_settings({"setup_hint_shown": True}, settings_file)
        settings = cfg.load_settings(settings_file)
        assert settings["telemetry_root"] == "D:\\a"
        assert settings["setup_hint_shown"] is True

    def test_save_creates_parent_directory(self, tmp_path):
        nested = str(tmp_path / "deep" / "dir" / "settings.json")
        cfg.save_settings({"a": 1}, nested)
        assert os.path.isfile(nested)

    def test_corrupt_file_does_not_raise(self, settings_file):
        with open(settings_file, "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        before = len(cfg.CONFIG_WARNINGS)
        assert cfg.load_settings(settings_file) == {}
        assert len(cfg.CONFIG_WARNINGS) > before, "a corrupt settings file must be reported"

    def test_non_object_json_is_rejected(self, settings_file):
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        assert cfg.load_settings(settings_file) == {}

    def test_written_file_is_valid_json(self, settings_file):
        cfg.save_settings({"telemetry_root": "D:\\x"}, settings_file)
        with open(settings_file, encoding="utf-8") as f:
            assert isinstance(json.load(f), dict)


class TestTelemetryRootPrecedence:
    """Environment beats settings, settings beat auto-detection."""

    def test_environment_wins(self, tmp_path, monkeypatch):
        env_dir = tmp_path / "env"
        env_dir.mkdir()
        monkeypatch.setenv("TENTHS_TELEMETRY_ROOT", str(env_dir))
        monkeypatch.setattr(cfg, "SETTINGS", {"telemetry_root": str(tmp_path / "settings")})
        assert cfg._resolve_telemetry_root() == os.path.normpath(str(env_dir))

    def test_settings_used_when_no_environment(self, tmp_path, monkeypatch):
        configured = tmp_path / "configured"
        configured.mkdir()
        monkeypatch.delenv("TENTHS_TELEMETRY_ROOT", raising=False)
        monkeypatch.setattr(cfg, "SETTINGS", {"telemetry_root": str(configured)})
        assert cfg._resolve_telemetry_root() == os.path.normpath(str(configured))

    def test_auto_detection_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv("TENTHS_TELEMETRY_ROOT", raising=False)
        monkeypatch.setattr(cfg, "SETTINGS", {})
        assert cfg._resolve_telemetry_root() == cfg._find_iracing_telemetry()

    def test_configured_but_missing_path_is_reported(self, tmp_path, monkeypatch):
        """A typo in the settings file must not fail silently."""
        monkeypatch.delenv("TENTHS_TELEMETRY_ROOT", raising=False)
        missing = str(tmp_path / "nope")
        monkeypatch.setattr(cfg, "SETTINGS", {"telemetry_root": missing})
        monkeypatch.setattr(cfg, "CONFIG_WARNINGS", [])
        resolved = cfg._resolve_telemetry_root()
        assert resolved == os.path.normpath(missing)
        assert cfg.CONFIG_WARNINGS, "a configured-but-missing folder must be reported"
        assert "tenths config" in cfg.CONFIG_WARNINGS[0]

    def test_settings_path_honours_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TENTHS_SETTINGS", str(tmp_path / "custom.json"))
        assert cfg._settings_path() == str(tmp_path / "custom.json")

    def test_settings_path_defaults_under_local_appdata(self, monkeypatch):
        monkeypatch.delenv("TENTHS_SETTINGS", raising=False)
        monkeypatch.setenv("LOCALAPPDATA", r"C:\fake\Local")
        assert cfg._settings_path() == os.path.join(r"C:\fake\Local", "Tenths", "settings.json")


class TestFirstRunGuidance:
    """A user with no telemetry must be told once, then left alone."""

    def _watcher(self, root):
        from tenths.service.watcher import TelemetryWatcher
        return TelemetryWatcher(telemetry_root=str(root), auto_open=False)

    def test_empty_root_has_no_telemetry(self, tmp_path):
        assert self._watcher(tmp_path)._has_any_telemetry() is False

    def test_ibt_in_root_counts_as_telemetry(self, tmp_path):
        (tmp_path / "car_track 2026-01-01 10-00-00.ibt").write_bytes(b"x")
        assert self._watcher(tmp_path)._has_any_telemetry() is True

    def test_archived_ibt_counts_as_telemetry(self, tmp_path):
        archive = tmp_path / "_archive"
        archive.mkdir()
        (archive / "car_track 2026-01-01 10-00-00.ibt").write_bytes(b"x")
        assert self._watcher(tmp_path)._has_any_telemetry() is True

    def test_processed_session_tree_counts_as_telemetry(self, tmp_path):
        (tmp_path / "bmwm2csr").mkdir()
        assert self._watcher(tmp_path)._has_any_telemetry() is True

    def test_hint_shown_once_and_recorded(self, tmp_path, monkeypatch):
        shown = []

        class FakeNotifier:
            def notify_info(self, title, message, **kw):
                shown.append((title, message))

        settings_path = str(tmp_path / "settings.json")
        monkeypatch.setattr(cfg, "SETTINGS_PATH", settings_path)
        monkeypatch.setattr(cfg, "SETTINGS", {})

        telemetry = tmp_path / "telemetry"
        telemetry.mkdir()
        w = self._watcher(telemetry)
        monkeypatch.setattr(w, "_get_notifier", lambda: FakeNotifier())

        w._check_first_run()
        assert len(shown) == 1
        assert "Alt+L" in shown[0][1]
        assert cfg.load_settings(settings_path).get("setup_hint_shown") is True

    def test_hint_not_repeated_once_recorded(self, tmp_path, monkeypatch):
        shown = []

        class FakeNotifier:
            def notify_info(self, title, message, **kw):
                shown.append(title)

        monkeypatch.setattr(cfg, "SETTINGS_PATH", str(tmp_path / "s.json"))
        monkeypatch.setattr(cfg, "SETTINGS", {"setup_hint_shown": True})

        telemetry = tmp_path / "telemetry"
        telemetry.mkdir()
        w = self._watcher(telemetry)
        monkeypatch.setattr(w, "_get_notifier", lambda: FakeNotifier())

        w._check_first_run()
        assert shown == [], "established users must not be nagged"

    def test_no_hint_when_telemetry_exists(self, tmp_path, monkeypatch):
        shown = []

        class FakeNotifier:
            def notify_info(self, title, message, **kw):
                shown.append(title)

        telemetry = tmp_path / "telemetry"
        telemetry.mkdir()
        (telemetry / "car_track 2026-01-01 10-00-00.ibt").write_bytes(b"x")
        w = self._watcher(telemetry)
        monkeypatch.setattr(w, "_get_notifier", lambda: FakeNotifier())
        w._check_first_run()
        assert shown == []

    def test_broken_notifier_does_not_stop_startup(self, tmp_path, monkeypatch):
        class BrokenNotifier:
            def notify_info(self, *a, **k):
                raise RuntimeError("winotify unavailable")

        monkeypatch.setattr(cfg, "SETTINGS_PATH", str(tmp_path / "s.json"))
        monkeypatch.setattr(cfg, "SETTINGS", {})
        telemetry = tmp_path / "telemetry"
        telemetry.mkdir()
        w = self._watcher(telemetry)
        monkeypatch.setattr(w, "_get_notifier", lambda: BrokenNotifier())
        w._check_first_run()   # must not raise


class TestNotifierInfo:

    def test_notify_info_exists_with_optional_action(self):
        import inspect
        from tenths.service.notifier import SessionNotifier
        params = inspect.signature(SessionNotifier.notify_info).parameters
        assert "title" in params and "message" in params
        assert "action_label" in params and "action_target" in params
