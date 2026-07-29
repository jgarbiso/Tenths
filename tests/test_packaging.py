"""
Tests for packaging configuration and build readiness.
Validates that all files needed for PyInstaller and Inno Setup are present and correct.
"""

import os
import sys
import importlib

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestPackagingFiles:
    """Verify all required packaging files exist."""

    def test_spec_file_exists(self):
        spec = os.path.join(PROJECT_ROOT, "installer", "tenths.spec")
        assert os.path.exists(spec), "PyInstaller spec file missing"

    def test_iss_file_exists(self):
        iss = os.path.join(PROJECT_ROOT, "installer", "tenths_setup.iss")
        assert os.path.exists(iss), "Inno Setup script missing"

    def test_build_script_exists(self):
        build = os.path.join(PROJECT_ROOT, "installer", "build.py")
        assert os.path.exists(build), "Build script missing"

    def test_icon_exists(self):
        icon = os.path.join(PROJECT_ROOT, "assets", "tenths.ico")
        assert os.path.exists(icon), "Application icon missing"

    def test_icon_is_valid(self):
        """Icon should be loadable by Pillow."""
        from PIL import Image
        icon = os.path.join(PROJECT_ROOT, "assets", "tenths.ico")
        img = Image.open(icon)
        assert img.size[0] >= 16

    def test_tracks_directory_has_files(self):
        """Track maps should be bundled with the app."""
        tracks_dir = os.path.join(PROJECT_ROOT, "tracks")
        assert os.path.isdir(tracks_dir)
        md_files = [f for f in os.listdir(tracks_dir) if f.endswith('.md')]
        assert len(md_files) >= 4, f"Expected 4+ track maps, found {len(md_files)}"

    def test_landmark_data_bundled(self):
        """The primary track data (trackLandmarksData.json) must ship in the package."""
        landmark_file = os.path.join(PROJECT_ROOT, "tenths", "data", "trackLandmarksData.json")
        assert os.path.exists(landmark_file), "Bundled landmark data missing — new users would have no track data"

    def test_landmark_data_has_tracks(self):
        """The bundled landmark data must contain iRacing tracks."""
        import json
        landmark_file = os.path.join(PROJECT_ROOT, "tenths", "data", "trackLandmarksData.json")
        with open(landmark_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        ir_tracks = [e for e in data['trackLandmarksData'] if 'irTrackName' in e]
        assert len(ir_tracks) >= 400, f"Expected 400+ iRacing tracks, found {len(ir_tracks)}"


class TestEntryPoints:
    """Verify all entry points import cleanly."""

    def test_tray_main_importable(self):
        """The tray entry point must import without error."""
        from tenths.service.tray import main
        assert callable(main)

    def test_cli_main_importable(self):
        """The CLI entry point must import without error."""
        from tenths.cli import main
        assert callable(main)

    def test_config_importable(self):
        """Config module must import and provide required constants."""
        from tenths.config import (
            TELEMETRY_ROOT, ARCHIVE_DIR, TRACKS_DIR,
            ICON_PATH, MIN_SESSION_SIZE, VERSION,
        )
        assert isinstance(TELEMETRY_ROOT, str)
        assert isinstance(VERSION, str)
        assert "0.9.0" in VERSION


class TestDependencies:
    """Verify all required dependencies are installed."""

    @pytest.mark.parametrize("module", [
        "pandas",
        "numpy",
        "irsdk",
        "watchdog",
        "winotify",
        "pystray",
        "PIL",
        "yaml",
    ])
    def test_dependency_importable(self, module):
        """Each dependency must be importable."""
        importlib.import_module(module)


class TestVersionConsistency:
    """Verify version is consistent across all locations."""

    def test_version_in_config(self):
        from tenths.config import VERSION
        assert VERSION == "0.9.0"

    def test_version_in_init(self):
        from tenths import __version__
        assert __version__ == "0.9.0"

    def test_version_in_pyproject(self):
        import tomllib
        pyproject = os.path.join(PROJECT_ROOT, "pyproject.toml")
        with open(pyproject, 'rb') as f:
            data = tomllib.load(f)
        assert data['project']['version'] == "0.9.0"


class TestSpecFileContent:
    """Validate PyInstaller spec file references correct paths."""

    def test_spec_references_tray_entry(self):
        spec = os.path.join(PROJECT_ROOT, "installer", "tenths.spec")
        with open(spec, 'r') as f:
            content = f.read()
        assert "tray.py" in content
        assert "tenths.ico" in content
        assert "tracks" in content

    def test_spec_bundles_landmark_data(self):
        """The spec must bundle tenths/data so new users get the 457-track database."""
        spec = os.path.join(PROJECT_ROOT, "installer", "tenths.spec")
        with open(spec, 'r') as f:
            content = f.read()
        assert "'data'" in content, "Spec must bundle the data folder (trackLandmarksData.json)"

    def test_spec_excludes_unnecessary(self):
        spec = os.path.join(PROJECT_ROOT, "installer", "tenths.spec")
        with open(spec, 'r') as f:
            content = f.read()
        assert "tkinter" in content  # should be in excludes
        assert "console=False" in content  # no console window
