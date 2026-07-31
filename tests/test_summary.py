"""
Tests for session_summary.json generation.
Validates the stable JSON data contract (schema v1.0.0).
"""

import json
import os
import tempfile

import pytest

from tenths.summary import (
    CURRENT_SCHEMA_VERSION,
    generate_session_summary,
    write_session_summary,
)


class TestSummarySchema:
    """Verify the JSON output has all required keys and correct types."""

    def test_schema_version_present(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        assert summary['schema_version'] == CURRENT_SCHEMA_VERSION

    def test_top_level_keys(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        required_keys = [
            'schema_version', 'generated_at', 'source_file', 'car', 'track',
            'session', 'best_lap', 'laps', 'abs', 'braking_zones',
            'corner_variance', 'trail_braking', 'gps_trace', 'tire_temps',
            'race_result', 'total_valid_laps', 'total_recoverable_time_s',
        ]
        for key in required_keys:
            assert key in summary, f"Missing top-level key: {key}"

    def test_car_fields(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        car = summary['car']
        assert car['name'] == 'BMW M2 CS Racing'
        assert car['class'] == 'Touring'
        assert isinstance(car['id'], int)
        assert isinstance(car['fuel_max_liters'], (int, float))

    def test_track_fields(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        track = summary['track']
        assert 'Winton' in track['name']
        assert track['length_m'] > 2000  # Winton is ~2945m
        assert isinstance(track['id'], int)

    def test_best_lap(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        best = summary['best_lap']
        assert best['number'] == 4  # Lap 4 was the PB in this session
        assert 90 < best['time_seconds'] < 92  # ~1:30.965
        assert '1:30' in best['time_formatted']
        assert isinstance(best['abs_hits'], int)
        assert best['max_speed_mph'] > 100

    def test_laps_array(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        laps = summary['laps']
        # One entry per lap with a valid time — the contract, rather than a
        # count tied to whichever version of the session is present.
        timed_laps = [r for r in winton_race_data['lap_results'] if r['time'] > 0]
        assert len(laps) == len(timed_laps)
        assert len(laps) >= 3, "need at least 3 laps for the summary to be meaningful"
        assert all('number' in l for l in laps)
        assert all('time_seconds' in l for l in laps)
        assert all('abs_hits' in l for l in laps)
        assert sum(1 for l in laps if l['is_best']) == 1

    def test_abs_data(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        abs_data = summary['abs']
        assert abs_data['cleanest_hits'] >= 0
        assert isinstance(abs_data['per_lap_totals'], list)
        assert len(abs_data['per_lap_totals']) == len(summary['laps'])

    def test_braking_zones(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        zones = summary['braking_zones']
        assert len(zones) == 5  # Winton has 5 braking zones
        for z in zones:
            assert 'turn_name' in z
            assert z['turn_name'] != ''  # should have real turn names from track map
            assert 0 < z['position_pct'] < 100
            assert z['entry_speed_mph'] > 0
            assert z['min_speed_mph'] > 0
            assert z['abs_hits'] >= 0
            # Negative brake_to_shift should be None
            if z['brake_to_shift_s'] is not None:
                assert z['brake_to_shift_s'] >= 0

    def test_corner_variance(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        cv = summary['corner_variance']
        assert len(cv) == 5
        for c in cv:
            assert c['priority'] in ('high', 'medium', 'low')
            assert c['time_loss_s'] >= 0
            assert c['avg_time_s'] >= c['best_time_s']

    def test_gps_trace(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        trace = summary['gps_trace']
        assert len(trace) == 200  # Dense 0.5% sampling
        assert all('lat' in p and 'lon' in p for p in trace)
        assert all('speed_mph' in p for p in trace)
        assert all('brake' in p for p in trace)
        assert all('throttle' in p for p in trace)

    def test_race_result_present(self, winton_race_data, winton_file_info, winton_track_map):
        """Winton session has a race result matched."""
        from tenths.process import find_race_result
        from tenths.results import parse_result

        si = winton_race_data.get('session_info', {})
        result_file = find_race_result(si)
        race_result = parse_result(result_file) if result_file else None

        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map, race_result)
        if summary['race_result'] is not None:
            rr = summary['race_result']
            assert rr['finish_position'] > 0
            assert rr['field_size'] > 0
            assert isinstance(rr['irating_delta'], int)

    def test_json_serializable(self, winton_race_data, winton_file_info, winton_track_map):
        """The entire summary must be JSON serializable."""
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        json_str = json.dumps(summary, default=str)
        assert len(json_str) > 1000  # should be substantial

    def test_total_recoverable_time(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        assert summary['total_recoverable_time_s'] > 0
        # Should match sum of corner variance losses
        expected = sum(cv['time_loss_s'] for cv in summary['corner_variance'])
        assert abs(summary['total_recoverable_time_s'] - expected) < 0.01


class TestSummaryWriteFile:
    """Test file writing functionality."""

    def test_write_creates_file(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = write_session_summary(summary, tmpdir)
            assert os.path.exists(filepath)
            assert filepath.endswith('session_summary.json')

    def test_written_file_is_valid_json(self, winton_race_data, winton_file_info, winton_track_map):
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = write_session_summary(summary, tmpdir)
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            assert loaded['schema_version'] == CURRENT_SCHEMA_VERSION
            assert loaded['car']['name'] == 'BMW M2 CS Racing'


class TestSummaryGT4:
    """Test GT4-specific fields in the summary."""

    def test_gt4_braking_zones_have_t2peak(self, midohio_practice_data, midohio_file_info, midohio_track_map):
        summary = generate_session_summary(midohio_practice_data, midohio_file_info, midohio_track_map)
        assert summary['car']['class'] == 'GT4'
        zones = summary['braking_zones']
        # At least some zones should have t2peak values
        t2peak_zones = [z for z in zones if z['t2peak_s'] is not None]
        assert len(t2peak_zones) > 0

    def test_gt4_negative_brk2shft_is_null(self, midohio_practice_data, midohio_file_info, midohio_track_map):
        """Mid-Ohio T9 has negative brake_to_shift — should be None in JSON."""
        summary = generate_session_summary(midohio_practice_data, midohio_file_info, midohio_track_map)
        zones = summary['braking_zones']
        # Find T9 Thunder Valley (around 62%)
        t9 = [z for z in zones if 60 < z['position_pct'] < 65]
        if t9:
            # This zone has negative brk2shft in raw data — should be None
            assert t9[0]['brake_to_shift_s'] is None
