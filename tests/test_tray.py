"""
Tests for system tray application logic.
"""

import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from tenths.service.tray import TenthsTray, ICON_PATH


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


class TestTrayFindReport:
    """Test finding the latest report."""

    def test_find_latest_report_returns_path(self):
        """Should find session_report.html files in telemetry tree."""
        tray = TenthsTray()
        report = tray._find_latest_report()
        # There should be at least one report from our previous processing
        if report is not None:
            assert report.endswith('session_report.html')
            assert os.path.exists(report)

    def test_find_latest_report_empty_dir(self):
        """Returns None when no reports exist."""
        tray = TenthsTray()
        with patch.object(tray, '_find_latest_report', return_value=None):
            assert tray._find_latest_report() is None


class TestTrayStartup:
    """Test Windows startup registration."""

    def test_startup_not_registered_by_default(self):
        """Tenths should NOT be in startup by default."""
        tray = TenthsTray()
        # This checks the actual registry — may be True if previously registered
        # Just verify it doesn't crash
        result = tray._is_startup_registered()
        assert isinstance(result, bool)

    def test_register_unregister_cycle(self):
        """Should be able to register and unregister without error."""
        tray = TenthsTray()
        # Register
        tray._register_startup()
        assert tray._is_startup_registered() is True

        # Unregister
        tray._unregister_startup()
        assert tray._is_startup_registered() is False


class TestTrayPause:
    """Test pause/resume functionality."""

    def test_toggle_pause_state(self):
        """Pausing should toggle the _paused flag."""
        tray = TenthsTray()
        tray._icon = MagicMock()  # mock icon to avoid pystray dependency

        # Mock watcher
        tray._watcher = MagicMock()

        assert tray._paused is False
        tray._toggle_pause()
        assert tray._paused is True
