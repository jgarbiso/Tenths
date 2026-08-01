"""
Tests for the Min Speed Spread (over-slowing) coaching metric.

Covers:
- analyzer._extract_apex_consistency() min-speed spread / over-braking math
- report.py DATA blob exposure of the new per-zone fields
- Summary View coaching priority (over-slowing outranks brake release shape)
- summary.py JSON contract fields
"""

import json

import numpy as np
import pandas as pd
import pytest

from tenths.analyzer import _extract_apex_consistency
from tenths.report import generate_report, _get_summary_js
from tenths.summary import generate_session_summary


MPS_PER_MPH = 1 / 2.237


def _mph_to_mps(mph):
    return mph * MPS_PER_MPH


def _make_df(lap_min_speeds_mph, zone_pct=50.0):
    """Build a telemetry DataFrame with a controlled min speed per lap.

    Each lap sweeps LapDistPct across the zone search window with a fixed
    high speed, except one sample at the zone center set to the target min.
    """
    rows = []
    for lap, min_mph in lap_min_speeds_mph.items():
        for pct in np.arange(zone_pct - 4, zone_pct + 7, 1.0):
            rows.append({'Lap': lap, 'LapDistPct': float(pct), 'Speed': _mph_to_mps(150.0)})
        rows.append({'Lap': lap, 'LapDistPct': zone_pct, 'Speed': _mph_to_mps(min_mph)})
    return pd.DataFrame(rows)


def _zones(zone_pct=50.0):
    return [{'pct': zone_pct}]


class TestAnalyzerMinSpeedSpread:
    """Production math for spread and over-braking."""

    def test_spread_is_fastest_minus_slowest_min_speed(self):
        """With a small sample the band is the true slowest/fastest."""
        df = _make_df({1: 80.0, 2: 90.0, 3: 100.0})
        result = _extract_apex_consistency(df, [1, 2, 3], _zones(), best_lap=3)
        assert result[0]['min_speed_spread_mph'] == pytest.approx(20.0, abs=0.2)
        assert result[0]['min_speed_worst_mph'] == pytest.approx(80.0, abs=0.2)
        assert result[0]['min_speed_typical_low_mph'] == pytest.approx(80.0, abs=0.2)
        assert result[0]['min_speed_typical_high_mph'] == pytest.approx(100.0, abs=0.2)

    def test_single_outlier_lap_does_not_dominate_spread(self):
        """One off-track lap must not report a huge spread for a repeatable corner."""
        speeds = {1: 90.0, 2: 91.0, 3: 90.5, 4: 89.5, 5: 90.0, 6: 91.0, 7: 25.0}
        df = _make_df(speeds)
        result = _extract_apex_consistency(df, list(speeds), _zones(), best_lap=2)
        # True range would be ~66mph; the percentile band must stay small.
        assert result[0]['min_speed_worst_mph'] == pytest.approx(25.0, abs=0.5)
        assert result[0]['min_speed_spread_mph'] < 15
        assert result[0]['min_speed_typical_low_mph'] > 40

    def test_genuine_wide_variation_still_reported(self):
        """A consistently wide range must still produce a large spread."""
        speeds = {1: 75.0, 2: 80.0, 3: 85.0, 4: 90.0, 5: 95.0, 6: 100.0}
        df = _make_df(speeds)
        result = _extract_apex_consistency(df, list(speeds), _zones(), best_lap=6)
        assert result[0]['min_speed_spread_mph'] > 15

    def test_band_low_never_exceeds_band_high(self):
        speeds = {1: 60.0, 2: 95.0, 3: 70.0, 4: 88.0, 5: 91.0, 6: 74.0}
        df = _make_df(speeds)
        zone = _extract_apex_consistency(df, list(speeds), _zones(), best_lap=2)[0]
        assert zone['min_speed_typical_low_mph'] <= zone['min_speed_typical_high_mph']
        assert zone['min_speed_spread_mph'] >= 0

    def test_incident_laps_excluded_from_aggregates(self):
        """Laps >10% slower than best must not skew the min-speed aggregates."""
        rows = []
        # Three clean laps at ~90mph min and 100s lap time
        for lap, min_mph in ((1, 90.0), (2, 91.0), (3, 89.0)):
            for pct in np.arange(46.0, 57.0, 1.0):
                rows.append({'Lap': lap, 'LapDistPct': float(pct),
                             'Speed': _mph_to_mps(150.0), 'LapLastLapTime': 100.0})
            rows.append({'Lap': lap, 'LapDistPct': 50.0,
                         'Speed': _mph_to_mps(min_mph), 'LapLastLapTime': 100.0})
        # One incident lap: 40% slower and crawling through the corner
        for pct in np.arange(46.0, 57.0, 1.0):
            rows.append({'Lap': 4, 'LapDistPct': float(pct),
                         'Speed': _mph_to_mps(150.0), 'LapLastLapTime': 140.0})
        rows.append({'Lap': 4, 'LapDistPct': 50.0,
                     'Speed': _mph_to_mps(20.0), 'LapLastLapTime': 140.0})
        df = pd.DataFrame(rows)

        zone = _extract_apex_consistency(df, [1, 2, 3, 4], _zones(), best_lap=3)[0]
        # The 20mph incident lap is excluded from aggregates...
        assert zone['min_speed_worst_mph'] == pytest.approx(89.0, abs=0.5)
        assert zone['min_speed_spread_mph'] < 5
        # ...but remains visible in the raw per-lap data
        assert len(zone['per_lap_apex']) == 4
        assert any(p['apex_speed_mph'] < 25 for p in zone['per_lap_apex'])

    def test_over_braking_is_best_lap_min_minus_average(self):
        # Best lap carries 100mph; the other laps average much lower.
        df = _make_df({1: 80.0, 2: 80.0, 3: 100.0})
        result = _extract_apex_consistency(df, [1, 2, 3], _zones(), best_lap=3)
        # avg = (80 + 80 + 100) / 3 = 86.67 -> 100 - 86.67 = 13.33
        assert result[0]['min_speed_best_mph'] == pytest.approx(100.0, abs=0.2)
        assert result[0]['over_braking_mph'] == pytest.approx(13.3, abs=0.3)

    def test_over_braking_negative_when_best_lap_is_slowest(self):
        """A best lap that is slowest through the corner must not flag over-slowing."""
        df = _make_df({1: 100.0, 2: 100.0, 3: 80.0})
        result = _extract_apex_consistency(df, [1, 2, 3], _zones(), best_lap=3)
        assert result[0]['over_braking_mph'] < 0

    def test_consistent_laps_have_zero_spread(self):
        df = _make_df({1: 90.0, 2: 90.0, 3: 90.0})
        result = _extract_apex_consistency(df, [1, 2, 3], _zones(), best_lap=1)
        assert result[0]['min_speed_spread_mph'] == pytest.approx(0.0, abs=0.2)
        assert result[0]['over_braking_mph'] == pytest.approx(0.0, abs=0.2)

    def test_single_lap_returns_none_metrics(self):
        df = _make_df({1: 90.0})
        result = _extract_apex_consistency(df, [1], _zones(), best_lap=1)
        assert result[0]['min_speed_spread_mph'] is None
        assert result[0]['over_braking_mph'] is None
        assert result[0]['min_speed_typical_low_mph'] is None
        assert result[0]['min_speed_typical_high_mph'] is None

    def test_no_zones_returns_empty_list(self):
        df = _make_df({1: 90.0, 2: 91.0})
        assert _extract_apex_consistency(df, [1, 2], [], best_lap=1) == []

    def test_missing_best_lap_leaves_over_braking_none_but_keeps_spread(self):
        df = _make_df({1: 80.0, 2: 100.0})
        result = _extract_apex_consistency(df, [1, 2], _zones(), best_lap=99)
        assert result[0]['over_braking_mph'] is None
        assert result[0]['min_speed_best_mph'] is None
        assert result[0]['min_speed_spread_mph'] == pytest.approx(20.0, abs=0.2)

    def test_values_are_native_python_floats(self):
        """Guards the RR-002 class of defect: no NumPy scalars in the contract."""
        df = _make_df({1: 80.0, 2: 100.0})
        zone = _extract_apex_consistency(df, [1, 2], _zones(), best_lap=2)[0]
        for key in ('min_speed_spread_mph', 'over_braking_mph',
                    'min_speed_best_mph', 'min_speed_worst_mph',
                    'min_speed_typical_low_mph', 'min_speed_typical_high_mph'):
            assert type(zone[key]) is float, f"{key} is {type(zone[key])}"
            assert not isinstance(zone[key], np.generic)

    def test_backward_compatible_apex_fields_retained(self):
        df = _make_df({1: 80.0, 2: 100.0})
        result = _extract_apex_consistency(df, [1, 2], _zones(), best_lap=2)
        assert result[0]['avg_apex_mph'] == pytest.approx(90.0, abs=0.3)
        assert result[0]['std_apex_mph'] is not None
        assert len(result[0]['per_lap_apex']) == 2


def _report_data(over_braking=None, spread=None, brake_linearity=0.9):
    """Minimal analyzer-shaped payload with one diagnosed corner."""
    return {
        'session_info': {'car_screen_name': 'BMW M4 GT3', 'track_display_name': 'Road Atlanta'},
        'lap_results': [
            {'lap': 1, 'time': 99.5, 'abs': 4, 'max_speed_mph': 150.0},
            {'lap': 2, 'time': 98.2, 'abs': 3, 'max_speed_mph': 151.0},
        ],
        'valid_laps': [1, 2],
        'best_lap': 2,
        'gps_trace': [],
        'gps_traces': {},
        'braking_zones': [{
            'pct': 50.0,
            'entry_pct': 48.0,
            'entry_mph': 150.0,
            'min_mph': 100.0,
            'max_brake': 96.0,
            'abs': 3,
            'dist_m': 2044.0,
            'lat': 33.0,
            'lon': -83.0,
            'brake_to_shift': 0.25,
            't2peak': 0.35,
            'coast_time': 0.1,
            'turnin_brake': 40.0,
            'apex_brake': 12.0,
            'apex_rpm': 5200.0,
            'max_ds_rpm': 6800.0,
            'notes': [],
        }],
        'corner_variance': [{'pct': 50.0, 'loss': 0.42, 'avg': 5.42, 'best': 5.0, 'std': 0.18}],
        'trail_braking': [],
        'per_lap_brake_points': [],
        'exit_metrics': [{'thr_on': 0.3, 'thr_lag': 0.2, 'brake_linearity': brake_linearity,
                          'brake_release_curve': [], 'brake_duration_s': 1.2}],
        'apex_consistency': [{
            'avg_apex_mph': 86.7,
            'std_apex_mph': 9.4,
            'per_lap_apex': [],
            'min_speed_best_mph': 100.0,
            'min_speed_worst_mph': 80.0,
            'min_speed_typical_low_mph': 80.0,
            'min_speed_typical_high_mph': 100.0,
            'min_speed_spread_mph': spread,
            'over_braking_mph': over_braking,
        }],
        'exit_metrics_all': {},
        'lap_abs_totals': [4, 3],
        'abs_trend': {},
        'tire_temps': {},
        'car_class': 'Touring',
        'track_length_m': 4088,
    }


def _file_info():
    return {'car': 'bmwm4gt3', 'track': 'roadatlanta_full', 'date': '2026-07-22', 'time': '20-57-09'}


def _extract_data_blob(html):
    start = html.index('const DATA = ') + len('const DATA = ')
    end = html.index(';\n', start)
    return json.loads(html[start:end])


class TestReportDataExposure:
    """The DATA blob must carry the new per-zone fields to the Summary View."""

    def test_min_speed_fields_present_in_data_blob(self):
        html = generate_report(_report_data(over_braking=13.3, spread=20.0), _file_info(), None)
        zone = _extract_data_blob(html)['braking_zones'][0]
        assert zone['min_speed_spread_mph'] == 20.0
        assert zone['over_braking_mph'] == 13.3
        assert zone['min_speed_best_mph'] == 100.0
        assert zone['min_speed_worst_mph'] == 80.0
        assert zone['min_speed_typical_low_mph'] == 80.0
        assert zone['min_speed_typical_high_mph'] == 100.0

    def test_fields_null_when_metric_unavailable(self):
        data = _report_data()
        data['apex_consistency'] = []
        html = generate_report(data, _file_info(), None)
        zone = _extract_data_blob(html)['braking_zones'][0]
        assert zone['min_speed_spread_mph'] is None
        assert zone['over_braking_mph'] is None

    def test_detailed_table_shows_average_min_speed(self):
        html = generate_report(_report_data(over_braking=13.3, spread=20.0), _file_info(), None)
        assert 'min-speed-avg' in html


class TestCoachingPriority:
    """Over-slowing must outrank brake release shape in the Summary View."""

    def test_over_braking_threshold_present(self):
        """Compared against a per-corner limit, not a fixed 8mph."""
        js = _get_summary_js()
        assert 'over_braking_mph' in js
        assert 'corner.over_braking_mph > corner.over_braking_limit_mph' in js

    def test_min_speed_spread_threshold_present(self):
        js = _get_summary_js()
        assert 'corner.min_speed_spread_mph > corner.spread_limit_mph' in js

    def test_thresholds_are_not_hardcoded_mph(self):
        """Guards the regression: fixed mph values fired on 5 of 8 real corners."""
        js = _get_summary_js()
        assert 'corner.min_speed_spread_mph > 10' not in js
        assert 'corner.over_braking_mph > 8' not in js
        assert 'corner.apex_std_mph > 4' not in js

    def test_over_braking_ranked_above_brake_linearity(self):
        js = _get_summary_js()
        start = js.index('function generateCoachingSentence')
        end = js.index('function getDiagnosisType')
        body = js[start:end]
        assert body.index('over_braking_mph') < body.index('brake_linearity')

    def test_min_speed_spread_ranked_above_apex_consistency(self):
        js = _get_summary_js()
        start = js.index('function generateCoachingSentence')
        end = js.index('function getDiagnosisType')
        body = js[start:end]
        assert body.index('min_speed_spread_mph') < body.index('apex_std_mph')

    def test_diagnosis_types_registered(self):
        js = _get_summary_js()
        start = js.index('function getDiagnosisType')
        body = js[start:start + 800]
        assert "'over_braking'" in body
        assert "'min_speed_spread'" in body
        assert body.index('over_braking_mph') < body.index('brake_linearity')

    def test_shared_corner_builder_used_everywhere(self):
        """Focus cards and Next Race Focus must use one corner builder."""
        js = _get_summary_js()
        assert 'function buildCorner' in js
        # buildCorner is defined once and called by both consumers
        assert js.count('function buildCorner') == 1
        assert js.count('buildCorner(') >= 3

    def test_coaching_sentence_mentions_over_slowing(self):
        js = _get_summary_js()
        assert 'Over-slowing' in js

    def test_coaching_sentence_mentions_min_speed_range(self):
        js = _get_summary_js()
        assert 'Min speed varies' in js

    def test_sentence_range_uses_the_same_band_as_the_spread(self):
        """The displayed range must come from the band that defines the spread."""
        js = _get_summary_js()
        start = js.index('function generateCoachingSentence')
        end = js.index('function getDiagnosisType')
        body = js[start:end]
        assert 'min_speed_typical_low_mph' in body
        assert 'min_speed_typical_high_mph' in body


class TestSummaryJsonContract:
    """session_summary.json must expose the metric for downstream consumers."""

    def test_summary_includes_min_speed_fields(self):
        summary = generate_session_summary(
            _report_data(over_braking=13.3, spread=20.0), _file_info(), None)
        zone = summary['braking_zones'][0]
        assert zone['min_speed_spread_mph'] == 20.0
        assert zone['over_braking_mph'] == 13.3
        assert zone['min_speed_best_mph'] == 100.0
        assert zone['min_speed_worst_mph'] == 80.0
        assert zone['min_speed_typical_low_mph'] == 80.0
        assert zone['min_speed_typical_high_mph'] == 100.0
        assert zone['apex_avg_mph'] == 86.7
        assert zone['apex_std_mph'] == 9.4

    def test_summary_fields_null_without_apex_data(self):
        data = _report_data()
        data['apex_consistency'] = []
        summary = generate_session_summary(data, _file_info(), None)
        zone = summary['braking_zones'][0]
        assert zone['min_speed_spread_mph'] is None
        assert zone['over_braking_mph'] is None

    def test_summary_remains_json_serializable(self):
        summary = generate_session_summary(
            _report_data(over_braking=13.3, spread=20.0), _file_info(), None)
        reloaded = json.loads(json.dumps(summary))
        assert reloaded['braking_zones'][0]['over_braking_mph'] == 13.3


class TestOverBrakingThresholdRR022:
    """RR-022: Retuned over-braking thresholds — 7% with 1.5 mph floor.

    Validated against 8 archived sessions (41 corners, 4 car models, 2.3–6.4 km).
    The old 20% / 6.0 mph threshold could never fire (peak was 31% of the limit).
    """

    def test_production_constants_match_decision(self):
        """The threshold constants must reflect the owner's retuning decision."""
        from tenths.analyzer import (
            OVER_BRAKING_LIMIT_FRACTION,
            OVER_BRAKING_LIMIT_FLOOR_MPH,
        )
        assert OVER_BRAKING_LIMIT_FRACTION == 0.07
        assert OVER_BRAKING_LIMIT_FLOOR_MPH == 1.5

    def test_spread_constants_untouched(self):
        """RR-021 validated spread independently; it must not drift."""
        from tenths.analyzer import (
            SPREAD_LIMIT_FRACTION,
            SPREAD_LIMIT_FLOOR_MPH,
        )
        assert SPREAD_LIMIT_FRACTION == 0.20
        assert SPREAD_LIMIT_FLOOR_MPH == 6.0

    def test_over_braking_fires_at_retuned_threshold(self):
        """A corner where the driver over-slows clearly at a 50 mph avg should fire.

        best_lap=3 carries 60 mph; others at 50 → avg ≈ 53.3, over_braking ≈ 6.7
        limit = max(0.07 * 53.3, 1.5) ≈ 3.7. 6.7 > 3.7 → fires.
        """
        df = _make_df({1: 50.0, 2: 50.0, 3: 60.0})
        result = _extract_apex_consistency(df, [1, 2, 3], _zones(), best_lap=3)
        zone = result[0]
        assert zone['over_braking_limit_mph'] == pytest.approx(3.7, abs=0.3)
        assert zone['over_braking_mph'] > zone['over_braking_limit_mph']

    def test_over_braking_does_not_fire_below_threshold(self):
        """A corner where the driver over-slows 2 mph at a 50 mph avg should not fire.

        limit = max(0.07 * 50.7, 1.5) ≈ 3.5. 2 < 3.5 → does not fire.
        """
        # best_lap=3 carries 52 mph; others at 50 → avg ≈ 50.7, over_braking ≈ 1.3
        df = _make_df({1: 50.0, 2: 50.0, 3: 52.0})
        result = _extract_apex_consistency(df, [1, 2, 3], _zones(), best_lap=3)
        zone = result[0]
        assert zone['over_braking_mph'] < zone['over_braking_limit_mph']

    def test_floor_prevents_trivial_flags_at_slow_corners(self):
        """At a 15 mph hairpin, 0.07 * 15 = 1.05, but the floor is 1.5.

        So a 1.2 mph over-braking should NOT fire.
        """
        df = _make_df({1: 15.0, 2: 15.0, 3: 16.5})
        result = _extract_apex_consistency(df, [1, 2, 3], _zones(), best_lap=3)
        zone = result[0]
        assert zone['over_braking_limit_mph'] == pytest.approx(1.5, abs=0.1)
        # over_braking = 16.5 - ~15.5 ≈ 1.0 → below the 1.5 floor
        assert zone['over_braking_mph'] < zone['over_braking_limit_mph']

    def test_no_hardcoded_over_braking_8_in_report_js(self):
        """The old hardcoded `> 8` and `> 4` absolute thresholds must be gone."""
        js = _get_summary_js()
        # The old pattern was: overBrk > 8 ? 'bad' : (overBrk > 4 ? 'warn'
        assert 'overBrk > 8' not in js
        assert 'overBrk > 4' not in js

    def test_no_hardcoded_fallback_8_in_buildCorner(self):
        """The ?? 8 fallback for over_braking_limit_mph must be gone."""
        js = _get_summary_js()
        assert 'over_braking_limit_mph ?? 8' not in js

    def test_detailed_view_uses_computed_limit(self):
        """The Detailed table's color logic must reference the computed limit."""
        from tenths.report import generate_report
        html = generate_report(
            _report_data(over_braking=5.0, spread=3.0), _file_info(), None)
        # The JS should reference overBrkLimit from the zone data
        assert 'overBrkLimit' in html

    def test_null_limit_suppresses_diagnosis(self):
        """When over_braking_limit_mph is null, no diagnosis should fire."""
        js = _get_summary_js()
        # The condition must check for null before comparing
        assert 'over_braking_limit_mph !== null' in js
