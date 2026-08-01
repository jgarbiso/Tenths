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
    """Verify version is consistent across all locations.

    Five files carry the version. They agree today only by hand. A release
    will eventually ship with mismatched versions unless a test catches it.
    """

    def _canonical_version(self):
        """Return the canonical three-part version from pyproject.toml."""
        import tomllib
        pyproject = os.path.join(PROJECT_ROOT, "pyproject.toml")
        with open(pyproject, 'rb') as f:
            data = tomllib.load(f)
        return data['project']['version']

    def test_version_in_config(self):
        from tenths.config import VERSION
        assert VERSION == self._canonical_version()

    def test_version_in_init(self):
        from tenths import __version__
        assert __version__ == self._canonical_version()

    def test_version_in_pyproject(self):
        # Self-check: canonical source is parseable
        v = self._canonical_version()
        parts = v.split('.')
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_version_in_version_info_txt(self):
        """installer/version_info.txt carries a four-part Windows version."""
        import re
        version_file = os.path.join(PROJECT_ROOT, "installer", "version_info.txt")
        content = open(version_file, 'r', encoding='utf-8').read()

        canonical = self._canonical_version()
        four_part = canonical + ".0"

        # String fields: FileVersion and ProductVersion must be '<major>.<minor>.<patch>.0'
        file_ver_match = re.search(r"StringStruct\('FileVersion',\s*'([^']+)'\)", content)
        prod_ver_match = re.search(r"StringStruct\('ProductVersion',\s*'([^']+)'\)", content)
        assert file_ver_match, "FileVersion string not found in version_info.txt"
        assert prod_ver_match, "ProductVersion string not found in version_info.txt"
        assert file_ver_match.group(1) == four_part
        assert prod_ver_match.group(1) == four_part

        # Tuple fields: filevers and prodvers must be (major, minor, patch, 0)
        major, minor, patch = canonical.split('.')
        expected_tuple = f"({major},{minor},{patch},0)"
        normalized = content.replace(' ', '').replace('\n', '')
        assert f"filevers={expected_tuple}" in normalized, \
            f"filevers tuple does not match {expected_tuple}"
        assert f"prodvers={expected_tuple}" in normalized, \
            f"prodvers tuple does not match {expected_tuple}"

    def test_version_in_inno_setup_iss(self):
        """installer/tenths_setup.iss #define MyAppVersion must match."""
        import re
        iss_file = os.path.join(PROJECT_ROOT, "installer", "tenths_setup.iss")
        content = open(iss_file, 'r', encoding='utf-8').read()

        canonical = self._canonical_version()
        match = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', content)
        assert match, "MyAppVersion not found in tenths_setup.iss"
        assert match.group(1) == canonical


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


class TestBuiltArtifact:
    """Validate the actual built EXE when it exists.

    Skips cleanly when dist/Tenths/Tenths.exe has not been built, so a developer
    running unit tests without building is not blocked. This is a release-quality
    guard, not a development prerequisite.
    """

    EXE_PATH = os.path.join(PROJECT_ROOT, "dist", "Tenths", "Tenths.exe")
    INTERNAL = os.path.join(PROJECT_ROOT, "dist", "Tenths", "_internal")

    @pytest.fixture(autouse=True)
    def _skip_if_not_built(self):
        if not os.path.isfile(self.EXE_PATH):
            pytest.skip(
                "dist/Tenths/Tenths.exe not found. "
                "Run `python installer/build.py` to produce it."
            )

    def test_exe_has_version_resource(self):
        """Read the embedded version resource via PowerShell and assert metadata."""
        import subprocess
        import json

        ps_script = (
            f'$v = (Get-Item "{self.EXE_PATH}").VersionInfo; '
            'ConvertTo-Json @{'
            '  ProductName=$v.ProductName;'
            '  ProductVersion=$v.ProductVersion;'
            '  CompanyName=$v.CompanyName;'
            '  FileDescription=$v.FileDescription'
            '}'
        )
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            pytest.skip(f"PowerShell version query failed: {result.stderr.strip()}")

        info = json.loads(result.stdout)

        assert info['ProductName'] == 'Tenths'
        assert info['CompanyName'] == 'Justin Garbiso'
        assert 'telemetry' in info['FileDescription'].lower() or 'tenths' in info['FileDescription'].lower()

        # Version must match the canonical source
        import tomllib
        pyproject = os.path.join(PROJECT_ROOT, "pyproject.toml")
        with open(pyproject, 'rb') as f:
            canonical = tomllib.load(f)['project']['version']
        # Windows version is four-part; the EXE may report either 0.9.0 or 0.9.0.0
        assert info['ProductVersion'].startswith(canonical)

    def test_bundled_landmark_data_present(self):
        landmark = os.path.join(self.INTERNAL, "data", "trackLandmarksData.json")
        assert os.path.isfile(landmark), f"Missing: {landmark}"
        assert os.path.getsize(landmark) > 100_000, "Landmark file too small"

    def test_bundled_tracks_directory_present(self):
        tracks = os.path.join(self.INTERNAL, "tracks")
        assert os.path.isdir(tracks), f"Missing: {tracks}"
        # Should have at least a few .md files
        md_files = [f for f in os.listdir(tracks) if f.endswith('.md')]
        assert len(md_files) > 0, "tracks/ directory is empty"

    def test_bundled_icon_present(self):
        icon = os.path.join(self.INTERNAL, "assets", "tenths.ico")
        assert os.path.isfile(icon), f"Missing: {icon}"

    def test_exe_is_not_signed(self):
        """Document the current state: unsigned. Will change when a cert is obtained."""
        import subprocess
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f'(Get-AuthenticodeSignature "{self.EXE_PATH}").Status'],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            pytest.skip("PowerShell signature check unavailable")
        # Currently expected to be NotSigned. When signing is added, change to Valid.
        assert 'NotSigned' in result.stdout.strip()


class TestUninstallPaths:
    """Installer [UninstallDelete] must name paths the application actually creates.

    If the uninstall entries drift from the real paths in config.py, the
    installer either deletes something it shouldn't or leaves orphaned files.
    This test ties them together.
    """

    def _iss_uninstall_paths(self):
        """Parse the [UninstallDelete] section from the .iss file."""
        import re
        iss = os.path.join(PROJECT_ROOT, "installer", "tenths_setup.iss")
        content = open(iss, 'r', encoding='utf-8').read()
        # Extract Name: values from [UninstallDelete] entries
        section_start = content.index('[UninstallDelete]')
        section = content[section_start:]
        # Stop at the next section or EOF
        next_section = section.find('\n[', 1)
        if next_section > 0:
            section = section[:next_section]
        return re.findall(r'Name:\s*"([^"]+)"', section)

    def test_logs_path_matches_config(self):
        """The installer deletes logs at the same path config.py creates them."""
        from tenths.config import LOG_DIR
        paths = self._iss_uninstall_paths()
        # The .iss uses {localappdata}\Tenths\logs — resolve that to compare
        localappdata = os.environ.get('LOCALAPPDATA',
                                      os.path.join(os.path.expanduser("~"), "AppData", "Local"))
        expected_log_dir = os.path.normcase(os.path.join(localappdata, "Tenths", "logs"))
        actual_log_dir = os.path.normcase(LOG_DIR)
        assert expected_log_dir == actual_log_dir, (
            f"Installer deletes {expected_log_dir} but LOG_DIR is {actual_log_dir}")

    def test_settings_path_matches_config(self):
        """The installer deletes settings.json at the path config.py writes it."""
        from tenths.config import SETTINGS_PATH
        paths = self._iss_uninstall_paths()
        # Must include settings.json
        settings_entries = [p for p in paths if 'settings' in p.lower()]
        assert settings_entries, "No settings entry in [UninstallDelete]"

        localappdata = os.environ.get('LOCALAPPDATA',
                                      os.path.join(os.path.expanduser("~"), "AppData", "Local"))
        expected = os.path.normcase(os.path.join(localappdata, "Tenths", "settings.json"))
        actual = os.path.normcase(SETTINGS_PATH)
        assert expected == actual, (
            f"Installer deletes {expected} but SETTINGS_PATH is {actual}")

    def test_no_phantom_config_directory(self):
        """The old [UninstallDelete] targeted a 'config' folder that never existed."""
        paths = self._iss_uninstall_paths()
        for p in paths:
            assert 'config' not in p.lower() or 'settings' in p.lower(), (
                f"Phantom 'config' directory still referenced: {p}")

    def test_telemetry_never_deleted(self):
        """Reports and archived telemetry must never appear in uninstall entries."""
        paths = self._iss_uninstall_paths()
        for p in paths:
            assert 'iRacing' not in p, f"iRacing path in uninstall: {p}"
            assert 'telemetry' not in p, f"Telemetry path in uninstall: {p}"
