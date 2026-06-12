"""
Error path and edge case tests.
Validates graceful handling of missing/malformed data.
"""

import pytest

from tenths.summary import generate_session_summary


class TestMissingData:
    """Test behavior when expected data is missing or None."""

    def _minimal_data(self):
        """Return the minimum valid data dict that analyze() would produce."""
        return {
            'filepath': 'test.ibt',
            'vehicle': 'testcar',
            'venue': 'testtrack',
            'car_class': 'Touring',
            'track_length_m': 3000,
            'sample_rate': 60,
            'total_rows': 5000,
            'valid_laps': [2, 3],
            'best_lap': 2,
            'worst_lap': 3,
            'lap_results': [
                {'lap': 2, 'time': 90.5, 'abs': 10, 'max_speed_mph': 100},
                {'lap': 3, 'time': 92.0, 'abs': 20, 'max_speed_mph': 98},
            ],
            'lap_abs_totals': [10, 20],
            'abs_trend': {'early_avg': 10, 'late_avg': 20, 'delta': 10},
            'braking_zones': [],
            'trail_braking': [],
            'corner_variance': [],
            'tire_temps': {},
            'gps_trace': [],
            'gps_traces': {},
            'per_lap_brake_points': [],
            'session_info': {},
        }

    def _minimal_file_info(self):
        return {'car': 'testcar', 'track': 'testtrack', 'date': '2026-01-01', 'time': '12-00-00', 'filename': 'test.ibt'}

    def test_no_track_map(self):
        """Should work fine with track_map=None (fallback to percentages)."""
        data = self._minimal_data()
        summary = generate_session_summary(data, self._minimal_file_info(), None)
        assert summary['schema_version'] == '1.0.0'
        assert summary['car']['name'] == 'testcar'

    def test_no_race_result(self):
        """race_result=None should produce null in output."""
        data = self._minimal_data()
        summary = generate_session_summary(data, self._minimal_file_info(), None, None)
        assert summary['race_result'] is None

    def test_empty_braking_zones(self):
        """No braking zones should produce empty array."""
        data = self._minimal_data()
        data['braking_zones'] = []
        summary = generate_session_summary(data, self._minimal_file_info(), None)
        assert summary['braking_zones'] == []

    def test_empty_gps_trace(self):
        """No GPS data should produce empty array."""
        data = self._minimal_data()
        data['gps_trace'] = []
        summary = generate_session_summary(data, self._minimal_file_info(), None)
        assert summary['gps_trace'] == []

    def test_empty_corner_variance(self):
        """No corner variance should produce empty array."""
        data = self._minimal_data()
        data['corner_variance'] = []
        summary = generate_session_summary(data, self._minimal_file_info(), None)
        assert summary['corner_variance'] == []
        assert summary['total_recoverable_time_s'] == 0

    def test_empty_tire_temps(self):
        """No tire temp data should produce empty dict."""
        data = self._minimal_data()
        data['tire_temps'] = {}
        summary = generate_session_summary(data, self._minimal_file_info(), None)
        assert summary['tire_temps'] == {}

    def test_session_info_missing_fields(self):
        """Missing session_info fields should use fallbacks."""
        data = self._minimal_data()
        data['session_info'] = {}  # Empty — all fields use defaults
        summary = generate_session_summary(data, self._minimal_file_info(), None)
        assert summary['car']['name'] == 'testcar'  # fallback from file_info
        assert summary['session']['type'] == 'Practice'  # default

    def test_single_lap_session(self):
        """Session with only 1 valid lap should still produce valid summary."""
        data = self._minimal_data()
        data['valid_laps'] = [2]
        data['lap_results'] = [{'lap': 2, 'time': 90.5, 'abs': 10, 'max_speed_mph': 100}]
        data['lap_abs_totals'] = [10]
        data['best_lap'] = 2
        data['worst_lap'] = 2
        summary = generate_session_summary(data, self._minimal_file_info(), None)
        assert summary['total_valid_laps'] == 1
        assert len(summary['laps']) == 1
        assert summary['best_lap']['number'] == 2


class TestAnalyzerErrorPaths:
    """Test analyzer behavior with invalid inputs."""

    def test_nonexistent_file(self):
        """analyze() should return None for missing files."""
        from tenths.analyzer import analyze
        result = analyze("C:\\nonexistent\\path\\fake.ibt")
        assert result is None

    def test_parse_filename_invalid(self):
        """parse_filename should return None for malformed names."""
        from tenths.process import parse_filename
        result = parse_filename("not_a_valid_filename.txt")
        assert result is None

    def test_parse_filename_valid(self):
        """parse_filename should correctly parse iRacing filename format."""
        from tenths.process import parse_filename
        result = parse_filename(r"c:\path\bmwm2csr_winton national 2026-06-06 22-26-36.ibt")
        assert result is not None
        assert result['car'] == 'bmwm2csr'
        assert result['track'] == 'winton_national'
        assert result['date'] == '2026-06-06'
        assert result['time'] == '22-26-36'
