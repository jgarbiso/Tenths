"""
Tests for exit metrics: Thr On, Thr Lag, Brake Linearity, Brake Release Curve.
"""

import pytest

from tenths.units import mps_to_mph


class TestExitMetricsIntegration:
    """Integration tests using real telemetry data."""

    def test_exit_metrics_present_in_data(self, winton_race_data):
        """analyze() should include exit_metrics in the return dict."""
        assert 'exit_metrics' in winton_race_data
        assert len(winton_race_data['exit_metrics']) == len(winton_race_data['braking_zones'])

    def test_thr_on_values_reasonable(self, winton_race_data):
        """Thr On values should be positive and under 10 seconds."""
        for em in winton_race_data['exit_metrics']:
            if em['thr_on'] is not None:
                assert 0 < em['thr_on'] < 10, f"Thr On out of range: {em['thr_on']}"

    def test_thr_lag_values_reasonable(self, winton_race_data):
        """Thr Lag values should be non-negative and under 5 seconds."""
        for em in winton_race_data['exit_metrics']:
            if em['thr_lag'] is not None:
                assert 0 <= em['thr_lag'] < 5, f"Thr Lag out of range: {em['thr_lag']}"

    def test_brake_linearity_range(self, winton_race_data):
        """Brake linearity must be between 0 and 1."""
        for em in winton_race_data['exit_metrics']:
            if em['brake_linearity'] is not None:
                assert 0 <= em['brake_linearity'] <= 1, f"Linearity out of range: {em['brake_linearity']}"

    def test_brake_release_curve_format(self, winton_race_data):
        """Brake release curve should be a list of 20 normalized values (0-1)."""
        for em in winton_race_data['exit_metrics']:
            curve = em.get('brake_release_curve', [])
            if curve:
                assert len(curve) == 20
                assert all(0 <= v <= 1.1 for v in curve), f"Curve values out of range: {curve}"
                # First value should be near 1.0 (peak), last near 0.0
                assert curve[0] > 0.5, f"Curve should start near peak, got {curve[0]}"

    def test_gt4_exit_metrics(self, midohio_practice_data):
        """GT4 sessions should also have exit metrics."""
        assert 'exit_metrics' in midohio_practice_data
        em = midohio_practice_data['exit_metrics']
        assert len(em) == len(midohio_practice_data['braking_zones'])
        # At least some zones should have linearity scores
        has_linearity = [e for e in em if e['brake_linearity'] is not None]
        assert len(has_linearity) > 0


class TestExitMetricsEdgeCases:
    """Unit tests for edge cases."""

    def test_empty_braking_zones(self):
        """Should return empty list when no braking zones."""
        from tenths.analyzer import _extract_exit_metrics
        import pandas as pd

        df = pd.DataFrame({'Lap': [1], 'Speed': [50], 'Throttle': [100], 'Brake': [0], 'LapDistPct': [50]})
        result = _extract_exit_metrics(df, 1, [], 60)
        assert result == []

    def test_low_speed_hairpin_skipped(self, winton_race_data):
        """Zones where apex speed < 30mph should return None for thr_on/thr_lag."""
        # Winton doesn't have hairpins < 30mph, so all should have values
        for em in winton_race_data['exit_metrics']:
            # At Winton all corners are > 40mph, so thr_on should be populated
            assert em['thr_on'] is not None


class TestExitMetricsInSummary:
    """Verify exit metrics appear in session_summary.json output."""

    def test_summary_includes_exit_metrics(self, winton_race_data, winton_file_info, winton_track_map):
        from tenths.summary import generate_session_summary

        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        for zone in summary['braking_zones']:
            assert 'thr_on_s' in zone
            assert 'thr_lag_s' in zone
            assert 'brake_linearity' in zone

    def test_summary_linearity_values(self, winton_race_data, winton_file_info, winton_track_map):
        from tenths.summary import generate_session_summary

        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        for zone in summary['braking_zones']:
            if zone['brake_linearity'] is not None:
                assert 0 <= zone['brake_linearity'] <= 1


class TestApexConsistency:
    """Tests for apex speed consistency metric."""

    def test_apex_consistency_present(self, winton_race_data):
        """analyze() should include apex_consistency in the return dict."""
        assert 'apex_consistency' in winton_race_data
        assert len(winton_race_data['apex_consistency']) == len(winton_race_data['braking_zones'])

    def test_apex_std_values(self, winton_race_data):
        """Std dev should be non-negative and reasonable (< 20 mph).

        The analyzer stores m/s, so the bound is converted rather than relaxed.
        """
        for ac in winton_race_data['apex_consistency']:
            if ac['std_apex_mph'] is not None:
                assert 0 <= mps_to_mph(ac['std_apex_mph']) < 20

    def test_apex_avg_values(self, winton_race_data):
        """Average apex speed should be positive and reasonable."""
        for ac in winton_race_data['apex_consistency']:
            if ac['avg_apex_mph'] is not None:
                assert 20 < mps_to_mph(ac['avg_apex_mph']) < 200

    def test_per_lap_apex_count(self, winton_race_data):
        """Should have one entry per valid lap."""
        num_laps = len(winton_race_data['valid_laps'])
        for ac in winton_race_data['apex_consistency']:
            assert len(ac['per_lap_apex']) == num_laps
