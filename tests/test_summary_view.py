"""
Tests for the Session Summary View feature.

Tests verify:
- generate_report() accepts and embeds progression data
- HTML output contains both view panels (summary + detailed)
- View switcher is present with correct structure
- Summary view is default active
- Coaching data embedded correctly
- VR readability standards (font sizes in CSS)
- Self-contained (no CDN deps in summary CSS)
"""

import json
import pytest

from tenths.report import generate_report, _get_summary_css, _get_summary_js


def _make_minimal_data():
    """Create minimal analyzer output for report generation."""
    return {
        'session_info': {'car_screen_name': 'BMW M4 GT4', 'track_display_name': 'Mid-Ohio'},
        'lap_results': [
            {'lap': 1, 'time': 99.5, 'abs': 12},
            {'lap': 2, 'time': 98.2, 'abs': 8},
            {'lap': 3, 'time': 97.8, 'abs': 6},
        ],
        'valid_laps': [1, 2, 3],
        'best_lap': 3,
        'gps_trace': [],
        'gps_traces': {},
        'braking_zones': [
            {'pct': 0.15, 'speed_mph': 95, 'min_speed_mph': 55},
            {'pct': 0.45, 'speed_mph': 110, 'min_speed_mph': 60},
        ],
        'corner_variance': [
            {'pct': 0.15, 'loss': 0.45, 'type': 'brake'},
            {'pct': 0.45, 'loss': 0.32, 'type': 'brake'},
            {'pct': 0.70, 'loss': 0.15, 'type': 'throttle'},
        ],
        'trail_braking': [],
        'per_lap_brake_points': [],
        'exit_metrics': [
            {'thr_on': 0.3, 'thr_lag': 0.4, 'brake_linearity': 0.45, 'brake_release_curve': [], 'brake_duration_s': 1.2},
            {'thr_on': 0.5, 'thr_lag': 0.6, 'brake_linearity': 0.75, 'brake_release_curve': [], 'brake_duration_s': 1.5},
        ],
        'apex_consistency': [
            {'std_apex_mph': 3.2, 'avg_apex_mph': 55.0},
            {'std_apex_mph': 5.1, 'avg_apex_mph': 60.0},
        ],
        'exit_metrics_all': {},
        'lap_abs_totals': [12, 8, 6],
        'abs_trend': {},
        'tire_temps': {},
        'car_class': 'GT4',
        'track_length_m': 3650,
    }


def _make_file_info():
    return {'car': 'bmwm4evogt4', 'track': 'midohio_full', 'date': '2026-06-13', 'time': '16-37-00'}


def _make_progression():
    return {
        'previous_session': {'date': '2026-06-12', 'best_lap_time_s': 98.5},
        'delta_vs_previous': {'lap_time_s': -0.7, 'cleanest_abs': -2, 'total_recoverable_s': -0.3},
        'alltime_best': {'lap_time_s': 97.8, 'date': '2026-06-13', 'is_new_pb': True},
        'session_count': 3,
        'trend': {'lap_times': [99.0, 98.5, 97.8], 'dates': ['2026-06-10', '2026-06-12', '2026-06-13'], 'abs_avgs': [15, 10, 8]},
    }


class TestReportWithProgression:
    """Test that generate_report accepts and embeds progression data."""

    def test_progression_none_produces_valid_html(self):
        """Report generates without errors when progression is None."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None, progression=None)
        assert '<!DOCTYPE html>' in html
        assert '"progression": null' in html

    def test_progression_dict_embedded_in_data(self):
        """Progression dict is embedded in the DATA JSON blob."""
        data = _make_minimal_data()
        prog = _make_progression()
        html = generate_report(data, _make_file_info(), None, progression=prog)
        assert '"progression"' in html
        assert '"delta_vs_previous"' in html
        assert '"is_new_pb": true' in html

    def test_backward_compatible_no_progression_arg(self):
        """Calling without progression arg still works (backward compatible)."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert '<!DOCTYPE html>' in html


class TestViewSwitcher:
    """Test the view switcher structure in generated HTML."""

    def test_view_switcher_present(self):
        """View switcher element with two tabs exists in HTML."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert 'class="view-switcher"' in html
        assert 'role="tablist"' in html

    def test_exactly_two_tabs(self):
        """Exactly two tab buttons: Summary and Detailed."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert 'data-view="summary"' in html
        assert 'data-view="detailed"' in html
        assert html.count('role="tab"') == 2

    def test_summary_is_default_active(self):
        """Summary tab has active class and aria-selected=true by default."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        # Summary tab: active + aria-selected true
        assert 'class="view-tab active" role="tab" aria-selected="true" data-view="summary"' in html
        # Detailed tab: not active
        assert 'class="view-tab" role="tab" aria-selected="false" data-view="detailed"' in html


class TestViewPanels:
    """Test that both view panels exist with correct structure."""

    def test_summary_panel_exists(self):
        """Summary view panel exists with active class."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert 'id="summary-view"' in html
        assert 'class="view-panel active"' in html

    def test_detailed_panel_exists(self):
        """Detailed view panel exists without active class."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert 'id="detailed-view"' in html

    def test_detailed_contains_existing_content(self):
        """Detailed view contains the existing report content (map, charts, tables)."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert 'id="track-map"' in html
        assert 'id="chart-brake-throttle"' in html
        assert 'id="braking-table"' in html
        assert 'id="lap-table"' in html

    def test_summary_contains_coaching_containers(self):
        """Summary view has hero-row, next-focus, and focus-cards containers."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert 'id="summary-heroes"' in html
        assert 'id="next-focus"' in html
        assert 'id="focus-cards"' in html


class TestSummaryCss:
    """Test the summary CSS for VR readability standards."""

    def test_hero_numbers_48px(self):
        """Hero numbers use minimum 48px font."""
        css = _get_summary_css()
        assert 'font-size: 48px' in css

    def test_focus_card_turn_24px(self):
        """Turn names in focus cards use 24px."""
        css = _get_summary_css()
        assert 'font-size: 24px' in css

    def test_focus_card_body_16px(self):
        """Body text in focus cards uses 16px minimum."""
        css = _get_summary_css()
        assert 'font-size: 16px' in css

    def test_view_tab_44px_targets(self):
        """View switcher tabs have 44px minimum touch targets."""
        css = _get_summary_css()
        assert 'min-height: 44px' in css
        assert 'min-width: 44px' in css

    def test_pit_wall_colors(self):
        """Summary CSS uses Pit Wall theme color variables."""
        css = _get_summary_css()
        assert 'var(--bg-surface)' in css
        assert 'var(--accent-green)' in css
        assert 'var(--accent-red)' in css
        assert 'var(--accent-blue)' in css

    def test_line_height_1_4(self):
        """Body text has line-height >= 1.4 for VR readability."""
        css = _get_summary_css()
        assert 'line-height: 1.4' in css or 'line-height: 1.5' in css

    def test_view_panel_show_hide(self):
        """View panels use display none/block for switching."""
        css = _get_summary_css()
        assert '.view-panel { display: none; }' in css
        assert '.view-panel.active { display: block; }' in css


class TestSummaryJs:
    """Test the summary JavaScript for correctness."""

    def test_localstorage_key_pattern(self):
        """localStorage key uses document.title for per-report persistence."""
        js = _get_summary_js()
        assert "tenths_view_" in js
        assert "document.title" in js

    def test_coaching_thresholds(self):
        """Coaching sentence uses correct thresholds."""
        js = _get_summary_js()
        assert 'brake_linearity < 0.6' in js or 'brake_linearity !== null && corner.brake_linearity < 0.6' in js
        assert 'apex_std_mph > 4' in js or 'apex_std_mph !== null && corner.apex_std_mph > 4' in js
        assert 'thr_lag > 0.5' in js or 'thr_lag !== null && corner.thr_lag > 0.5' in js
        assert 'spread_meters > 15' in js or 'spread_meters !== null && corner.spread_meters > 15' in js

    def test_corner_filter_threshold(self):
        """Corners are filtered at 0.1s loss threshold."""
        js = _get_summary_js()
        assert 'loss > 0.1' in js

    def test_top_3_limit(self):
        """Only top 3 corners are shown."""
        js = _get_summary_js()
        assert '.slice(0, 3)' in js

    def test_drill_down_function(self):
        """Drill-down function exists and switches to detailed view."""
        js = _get_summary_js()
        assert 'function drillDown' in js
        assert 'switchToDetailed' in js

    def test_truncate_120_chars(self):
        """Coaching sentences are truncated at 120 characters."""
        js = _get_summary_js()
        assert '120' in js

    def test_first_session_fallback(self):
        """Shows 'First Session' when progression is null."""
        js = _get_summary_js()
        assert 'First Session' in js

    def test_consistent_session_message(self):
        """Shows 'No significant time loss' when no qualifying corners."""
        js = _get_summary_js()
        assert 'No significant time loss detected' in js

    def test_highlight_animation(self):
        """Drill-down adds highlight-row class for visual feedback."""
        js = _get_summary_js()
        assert 'highlight-row' in js

    def test_no_external_deps_in_summary(self):
        """Summary JS has no external library dependencies (no CDN calls)."""
        js = _get_summary_js()
        # Should not actually USE leaflet or chart.js (comments about them are fine)
        assert 'L.map(' not in js
        assert 'new Chart(' not in js
        assert 'chart.js' not in js.lower()
        assert 'cdn' not in js.lower()


class TestSelfContainedOutput:
    """Test that the report remains a single self-contained HTML file."""

    def test_single_html_file(self):
        """Output is a complete HTML document."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert html.startswith('<!DOCTYPE html>')
        assert '</html>' in html

    def test_summary_css_inline(self):
        """Summary CSS is embedded inline in the HTML."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert '.view-switcher' in html
        assert '.hero-value' in html
        assert '.focus-card' in html

    def test_summary_js_inline(self):
        """Summary JS is embedded inline in the HTML."""
        data = _make_minimal_data()
        html = generate_report(data, _make_file_info(), None)
        assert 'buildCoachingData' in html
        assert 'generateCoachingSentence' in html
        assert 'renderHeroes' in html
