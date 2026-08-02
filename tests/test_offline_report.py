"""
Tests for RR-009: Fully offline HTML session reports.

Validates that:
- Generated reports contain no external CDN/https references in asset positions
- Vendored asset files exist at expected paths
- The PyInstaller spec includes vendor assets in the datas list
"""

import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestVendorAssetsExist:
    """Verify all vendored assets are committed at the expected paths."""

    VENDOR_DIR = os.path.join(PROJECT_ROOT, 'tenths', 'assets', 'vendor')

    EXPECTED_FILES = [
        'leaflet.js',
        'leaflet.css',
        'chart.umd.min.js',
        'orbitron-700.woff2',
        'orbitron-900.woff2',
        'inter-400.woff2',
        'inter-500.woff2',
        'inter-600.woff2',
        'jetbrainsmono-400.woff2',
        'jetbrainsmono-500.woff2',
        'jetbrainsmono-600.woff2',
        'jetbrainsmono-700.woff2',
    ]

    def test_vendor_directory_exists(self):
        assert os.path.isdir(self.VENDOR_DIR), f"Vendor directory missing: {self.VENDOR_DIR}"

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_vendor_file_exists(self, filename):
        path = os.path.join(self.VENDOR_DIR, filename)
        assert os.path.isfile(path), f"Vendor file missing: {path}"

    @pytest.mark.parametrize("filename", EXPECTED_FILES)
    def test_vendor_file_not_empty(self, filename):
        path = os.path.join(self.VENDOR_DIR, filename)
        assert os.path.getsize(path) > 100, f"Vendor file is suspiciously small: {path}"


class TestSpecIncludesVendorAssets:
    """Verify the PyInstaller spec bundles vendor assets."""

    def test_spec_includes_vendor_datas(self):
        spec_path = os.path.join(PROJECT_ROOT, 'installer', 'tenths.spec')
        with open(spec_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Must reference the vendor directory in the datas list
        assert 'vendor' in content, "Spec file does not reference vendor assets"
        assert "tenths', 'assets', 'vendor'" in content or \
               "tenths\\\\assets\\\\vendor" in content or \
               "tenths/assets/vendor" in content, \
            "Spec file does not include tenths/assets/vendor in datas"


class TestReportHasNoExternalAssets:
    """Verify generated HTML contains no external CDN/https asset references."""

    @pytest.fixture()
    def generated_html(self):
        """Generate a minimal report to test for external references."""
        from tenths.report import generate_report
        from tenths.track_map import load_track_map

        # Minimal data structure that generate_report requires
        data = {
            'session_info': {
                'car_screen_name': 'Test Car',
                'track_display_name': 'Test Track',
                'track_config_name': '',
            },
            'lap_results': [
                {'lap': 1, 'time': 90.123, 'abs': 2},
                {'lap': 2, 'time': 91.456, 'abs': 1},
            ],
            'gps_trace': [{'lat': 0, 'lon': 0, 'speed': 100, 'brake': 0, 'throttle': 80, 'gear': 3, 'pct': 0}],
            'gps_traces': {},
            'braking_zones': [],
            'corner_variance': [],
            'trail_braking': [],
            'per_lap_brake_points': [],
            'exit_metrics': [],
            'apex_consistency': [],
            'exit_metrics_all': {},
            'valid_laps': [1, 2],
            'best_lap': 1,
            'track_length_m': 3000,
            'lap_abs_totals': [],
            'abs_trend': {},
            'tire_temps': {},
            'car_class_display': 'GT3',
            'physics_profile': 'GT3',
            'car_class': 'GT3',
        }
        file_info = {'car': 'test_car', 'track': 'test_track', 'date': '2026-01-01', 'time': '12-00-00'}
        track_map = {'turns': [], 'start': None}

        html = generate_report(data, file_info, track_map)
        return html

    def test_no_https_in_link_tags(self, generated_html):
        """No <link> tags should reference external URLs."""
        link_tags = re.findall(r'<link[^>]+>', generated_html)
        for tag in link_tags:
            assert 'https://' not in tag, f"External link found: {tag}"
            assert 'http://' not in tag, f"External link found: {tag}"

    def test_no_https_in_script_src(self, generated_html):
        """No <script> tags should have external src attributes."""
        script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', generated_html)
        for src in script_srcs:
            assert not src.startswith('http'), f"External script src: {src}"

    def test_no_google_fonts_reference(self, generated_html):
        """No reference to Google Fonts CDN."""
        assert 'fonts.googleapis.com' not in generated_html
        assert 'fonts.gstatic.com' not in generated_html

    def test_no_unpkg_reference(self, generated_html):
        """No reference to unpkg CDN."""
        assert 'unpkg.com' not in generated_html

    def test_no_jsdelivr_reference(self, generated_html):
        """No reference to jsDelivr CDN."""
        assert 'jsdelivr.net' not in generated_html

    def test_contains_inline_leaflet(self, generated_html):
        """Report should contain inlined Leaflet code."""
        # Leaflet declares L.map — check for characteristic Leaflet content
        assert 'L.map' in generated_html or 'L.Map' in generated_html

    def test_contains_inline_chartjs(self, generated_html):
        """Report should contain inlined Chart.js code."""
        assert 'Chart' in generated_html

    def test_contains_inline_font_face(self, generated_html):
        """Report should contain @font-face declarations with data URIs."""
        assert '@font-face' in generated_html
        assert 'data:font/woff2;base64,' in generated_html

    def test_contains_orbitron_font(self, generated_html):
        """Orbitron font must be embedded."""
        assert "font-family: 'Orbitron'" in generated_html

    def test_contains_inter_font(self, generated_html):
        """Inter font must be embedded."""
        assert "font-family: 'Inter'" in generated_html

    def test_contains_jetbrains_mono_font(self, generated_html):
        """JetBrains Mono font must be embedded."""
        assert "font-family: 'JetBrains Mono'" in generated_html
