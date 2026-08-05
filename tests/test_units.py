"""
Tests for the SI-internal / display-units split.

The analyzer stores SI (m/s, °C). Consumers convert at their own boundary. These
tests pin that contract down so a future change cannot silently reintroduce an
inline conversion in the analysis path or drop one at a display boundary.
"""

import pytest

from tenths import units
from tenths.units import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    kph_to_mps,
    metres_to_km,
    metres_to_miles,
    mph_to_mps,
    mps_to_kph,
    mps_to_mph,
    speed_display,
    temp_display,
    to_display_units,
)


class TestScalarConversions:
    def test_mps_to_mph_known_value(self):
        assert mps_to_mph(10.0) == pytest.approx(22.37, abs=0.01)

    def test_mps_to_kph_is_exact(self):
        assert mps_to_kph(10.0) == 36.0

    def test_mph_round_trip(self):
        assert mph_to_mps(mps_to_mph(17.3)) == pytest.approx(17.3, abs=1e-9)

    def test_kph_round_trip(self):
        assert kph_to_mps(mps_to_kph(17.3)) == pytest.approx(17.3, abs=1e-9)

    def test_celsius_to_fahrenheit_known_values(self):
        assert celsius_to_fahrenheit(0) == 32.0
        assert celsius_to_fahrenheit(100) == 212.0

    def test_temperature_round_trip(self):
        assert fahrenheit_to_celsius(celsius_to_fahrenheit(85.0)) == pytest.approx(85.0, abs=1e-9)

    def test_distance_conversions(self):
        assert metres_to_km(2945) == pytest.approx(2.945, abs=1e-9)
        assert metres_to_miles(1609.344) == pytest.approx(1.0, abs=1e-9)


class TestConversionFactorIsPinned:
    """The factor must not drift without a deliberate decision.

    2.237 is what the analyzer used inline before speeds moved to SI. Changing it
    to the physically exact 2.2369362920544 would alter every displayed speed, so
    it is pinned here and the correction is tracked in POST_MVP.md.
    """

    def test_mps_to_mph_factor(self):
        assert units.MPS_TO_MPH == 2.237

    def test_mps_to_kph_factor(self):
        assert units.MPS_TO_KPH == 3.6


class TestDisplayHelpers:
    def test_speed_display_imperial(self):
        value, label = speed_display(10.0)
        assert label == "mph"
        assert value == pytest.approx(22.37, abs=0.01)

    def test_speed_display_metric(self):
        value, label = speed_display(10.0, metric=True)
        assert label == "km/h"
        assert value == 36.0

    def test_temp_display_imperial(self):
        value, label = temp_display(100.0)
        assert label == "°F"
        assert value == 212.0

    def test_temp_display_metric_passes_through(self):
        value, label = temp_display(100.0, metric=True)
        assert label == "°C"
        assert value == 100.0


class TestAnalyzerIsSI:
    """The analysis pipeline must not convert to display units internally."""

    def test_braking_zone_speeds_are_si(self, winton_race_data):
        """Entry speeds are m/s, so a ~117mph corner reads ~52."""
        entry = winton_race_data['braking_zones'][0]['entry_mph']
        assert 10 < entry < 100, f"expected m/s, got {entry} (looks like mph)"

    def test_lap_max_speed_is_si(self, winton_race_data):
        max_speed = winton_race_data['lap_results'][0]['max_speed_mph']
        assert 20 < max_speed < 120, f"expected m/s, got {max_speed}"

    def test_tire_temps_are_celsius(self, winton_race_data):
        temps = winton_race_data.get('tire_temps') or {}
        if not temps:
            pytest.skip("fixture has no tire temperature channels")
        avg = next(iter(temps.values()))['avg']
        assert 0 < avg < 130, f"expected °C, got {avg} (looks like °F)"

    def test_no_inline_mph_conversion_in_analysis_path(self):
        """The data path must not multiply by a display factor.

        The legacy print-based CLI still formats mph, but it does so through
        `mps_to_mph`, not a bare literal.
        """
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'tenths', 'analyzer.py')
        source = open(path, encoding='utf-8').read()
        assert '* 2.237' not in source, "inline mph conversion reintroduced in analyzer"
        assert '9/5+32' not in source, "inline °F conversion reintroduced in analyzer"


class TestToDisplayUnits:
    """The conversion boundary must cover every speed-bearing field."""

    def _si_data(self):
        return {
            'lap_results': [{'lap': 1, 'max_speed_mph': 50.0}],
            'braking_zones': [{'pct': 6.0, 'entry_mph': 52.0, 'min_mph': 33.0}],
            'apex_consistency': [{
                'avg_apex_mph': 29.0,
                'std_apex_mph': 0.76,
                'spread_limit_mph': 5.8,
                'over_braking_limit_mph': 2.03,
                'apex_std_limit_mph': 2.32,
                'min_speed_spread_mph': 1.98,
                'over_braking_mph': 1.3,
                'min_speed_best_mph': 30.0,
                'min_speed_worst_mph': 28.0,
                'min_speed_typical_low_mph': 28.0,
                'min_speed_typical_high_mph': 30.0,
                'per_lap_apex': [{'lap': 1, 'apex_speed_mph': 29.5}],
            }],
            'gps_trace': [{'pct': 0.0, 'speed_mph': 48.0}],
            'gps_traces': {'1': [{'pct': 0.0, 'speed_mph': 48.0}]},
            'per_lap_brake_points': [
                {'zone_pct': 6.0, 'entries': [{'lap': 1, 'speed_mph': 52.0}]}
            ],
            'tire_temps': {'LF': {'inner': 50.0, 'mid': 49.0, 'outer': 48.0, 'avg': 49.0}},
        }

    def test_braking_zones_converted(self):
        out = to_display_units(self._si_data())
        assert out['braking_zones'][0]['entry_mph'] == pytest.approx(116.3, abs=0.1)

    def test_lap_results_converted(self):
        out = to_display_units(self._si_data())
        assert out['lap_results'][0]['max_speed_mph'] == pytest.approx(111.85, abs=0.05)

    def test_apex_fields_converted_and_rounded_to_1dp(self):
        out = to_display_units(self._si_data())
        apex = out['apex_consistency'][0]
        assert apex['avg_apex_mph'] == pytest.approx(64.9, abs=0.05)
        # Rounded to 1dp, matching what consumers received before the refactor
        assert apex['std_apex_mph'] == round(apex['std_apex_mph'], 1)

    def test_per_lap_apex_converted(self):
        out = to_display_units(self._si_data())
        per_lap = out['apex_consistency'][0]['per_lap_apex'][0]
        assert per_lap['apex_speed_mph'] == pytest.approx(66.0, abs=0.1)

    def test_gps_traces_converted(self):
        out = to_display_units(self._si_data())
        assert out['gps_trace'][0]['speed_mph'] == pytest.approx(107.4, abs=0.1)
        assert out['gps_traces']['1'][0]['speed_mph'] == pytest.approx(107.4, abs=0.1)

    def test_nested_brake_point_entries_converted(self):
        """Regression: speeds live in the nested `entries` list, not on the zone."""
        out = to_display_units(self._si_data())
        zone = out['per_lap_brake_points'][0]
        assert zone['entries'][0]['speed_mph'] == pytest.approx(116.3, abs=0.1)
        assert 'speed_mph' not in zone, "must not invent a zone-level speed key"

    def test_tire_temps_converted(self):
        out = to_display_units(self._si_data())
        assert out['tire_temps']['LF']['mid'] == pytest.approx(120.2, abs=0.1)

    def test_tire_temp_average_is_mean_of_converted_corners(self):
        """Averaging converted corners, not converting the average, is what the
        pre-refactor code did; the two differ by one ULP."""
        out = to_display_units(self._si_data())
        lf = out['tire_temps']['LF']
        assert lf['avg'] == (lf['inner'] + lf['mid'] + lf['outer']) / 3

    def test_input_is_not_mutated(self):
        data = self._si_data()
        to_display_units(data)
        assert data['braking_zones'][0]['entry_mph'] == 52.0
        assert data['per_lap_brake_points'][0]['entries'][0]['speed_mph'] == 52.0

    def test_metric_mode_uses_kph(self):
        out = to_display_units(self._si_data(), metric=True)
        assert out['braking_zones'][0]['entry_mph'] == pytest.approx(187.2, abs=0.1)

    def test_metric_mode_leaves_celsius(self):
        out = to_display_units(self._si_data(), metric=True)
        assert out['tire_temps']['LF']['mid'] == 49.0


class TestSummaryContractStaysImperial:
    """The JSON summary is a machine contract; it stays mph regardless of the
    user's display preference, so the index and progression logic keep working."""

    def test_summary_speeds_are_mph_even_in_metric_mode(self, monkeypatch,
                                                        winton_race_data,
                                                        winton_file_info,
                                                        winton_track_map):
        import tenths.summary as summary_mod

        monkeypatch.setattr('tenths.config.UNITS', 'metric', raising=False)
        summary = summary_mod.generate_session_summary(
            winton_race_data, winton_file_info, winton_track_map, None)

        entry = summary['braking_zones'][0]['entry_speed_mph']
        assert 60 < entry < 250, f"summary should stay mph, got {entry}"

    def test_summary_schema_version_unchanged(self):
        from tenths.summary import CURRENT_SCHEMA_VERSION
        assert CURRENT_SCHEMA_VERSION == "1.0.0", (
            "summary content did not change, so the schema version must not move")
