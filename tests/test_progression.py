"""
Tests for session progression computation.
"""

import json
import os
import tempfile

import pytest

from tenths.summary import compute_progression, generate_session_summary, write_session_summary


class TestProgressionComputation:
    """Test the progression calculation logic."""

    def _create_mock_session_dir(self, tmpdir, dates_and_times):
        """Create mock session directories with summary JSON files.

        Args:
            tmpdir: temp directory (acts as car/track root)
            dates_and_times: list of (date_str, best_lap_time_seconds, cleanest_abs)
        """
        for date, time_s, abs_val in dates_and_times:
            date_dir = os.path.join(tmpdir, date)
            os.makedirs(date_dir, exist_ok=True)
            summary = {
                'schema_version': '1.0.0',
                'session': {'date': date},
                'best_lap': {'time_seconds': time_s},
                'abs': {'cleanest_hits': abs_val, 'per_lap_totals': [abs_val, abs_val + 10]},
                'total_recoverable_time_s': 1.5,
            }
            with open(os.path.join(date_dir, 'session_summary.json'), 'w') as f:
                json.dump(summary, f)

    def test_no_previous_sessions(self):
        """Returns None when no previous sessions exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, '2026-06-06')
            os.makedirs(session_dir)
            summary = {
                'session': {'date': '2026-06-06'},
                'best_lap': {'time_seconds': 91.0},
                'abs': {'cleanest_hits': 30, 'per_lap_totals': [30, 40]},
                'total_recoverable_time_s': 1.0,
            }
            result = compute_progression(summary, session_dir)
            assert result is None

    def test_with_previous_sessions(self):
        """Returns progression data when previous sessions exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create previous sessions
            self._create_mock_session_dir(tmpdir, [
                ('2026-06-01', 92.5, 50),
                ('2026-06-03', 91.8, 40),
            ])

            # Current session
            session_dir = os.path.join(tmpdir, '2026-06-06')
            os.makedirs(session_dir)
            summary = {
                'session': {'date': '2026-06-06'},
                'best_lap': {'time_seconds': 91.0},
                'abs': {'cleanest_hits': 30, 'per_lap_totals': [30, 40]},
                'total_recoverable_time_s': 1.0,
            }

            result = compute_progression(summary, session_dir)
            assert result is not None
            assert result['session_count'] == 3
            assert result['previous_session']['date'] == '2026-06-03'
            assert result['previous_session']['best_lap_time_s'] == 91.8

    def test_delta_vs_previous(self):
        """Delta should be negative when current session is faster."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_mock_session_dir(tmpdir, [
                ('2026-06-01', 92.0, 50),
            ])

            session_dir = os.path.join(tmpdir, '2026-06-06')
            os.makedirs(session_dir)
            summary = {
                'session': {'date': '2026-06-06'},
                'best_lap': {'time_seconds': 91.0},
                'abs': {'cleanest_hits': 30, 'per_lap_totals': [30]},
                'total_recoverable_time_s': 1.0,
            }

            result = compute_progression(summary, session_dir)
            assert result['delta_vs_previous']['lap_time_s'] == -1.0  # 1 second faster
            assert result['delta_vs_previous']['cleanest_abs'] == -20  # 20 fewer ABS

    def test_alltime_best_detection(self):
        """Should correctly identify if current session is a new PB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_mock_session_dir(tmpdir, [
                ('2026-06-01', 92.0, 50),
                ('2026-06-03', 91.5, 40),
            ])

            # Current is fastest ever
            session_dir = os.path.join(tmpdir, '2026-06-06')
            os.makedirs(session_dir)
            summary = {
                'session': {'date': '2026-06-06'},
                'best_lap': {'time_seconds': 90.9},
                'abs': {'cleanest_hits': 25, 'per_lap_totals': [25]},
                'total_recoverable_time_s': 0.8,
            }

            result = compute_progression(summary, session_dir)
            assert result['alltime_best']['is_new_pb'] is True
            assert result['alltime_best']['lap_time_s'] == 90.9

    def test_not_a_pb(self):
        """Should correctly identify when current is NOT a new PB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_mock_session_dir(tmpdir, [
                ('2026-06-01', 89.0, 20),  # Previous was faster
            ])

            session_dir = os.path.join(tmpdir, '2026-06-06')
            os.makedirs(session_dir)
            summary = {
                'session': {'date': '2026-06-06'},
                'best_lap': {'time_seconds': 91.0},
                'abs': {'cleanest_hits': 30, 'per_lap_totals': [30]},
                'total_recoverable_time_s': 1.0,
            }

            result = compute_progression(summary, session_dir)
            assert result['alltime_best']['is_new_pb'] is False
            assert result['alltime_best']['lap_time_s'] == 89.0

    def test_trend_arrays(self):
        """Trend arrays should be ordered oldest→newest including current."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._create_mock_session_dir(tmpdir, [
                ('2026-06-01', 93.0, 60),
                ('2026-06-03', 92.0, 45),
                ('2026-06-05', 91.5, 35),
            ])

            session_dir = os.path.join(tmpdir, '2026-06-06')
            os.makedirs(session_dir)
            summary = {
                'session': {'date': '2026-06-06'},
                'best_lap': {'time_seconds': 91.0},
                'abs': {'cleanest_hits': 30, 'per_lap_totals': [30, 35]},
                'total_recoverable_time_s': 0.9,
            }

            result = compute_progression(summary, session_dir)
            assert result['trend']['dates'] == ['2026-06-01', '2026-06-03', '2026-06-05', '2026-06-06']
            assert result['trend']['lap_times'] == [93.0, 92.0, 91.5, 91.0]
            assert len(result['trend']['abs_avgs']) == 4


class TestProgressionInSummaryWrite:
    """Test that progression is included when writing session_summary.json."""

    def test_write_includes_progression_key(self, winton_race_data, winton_file_info, winton_track_map):
        """Written JSON should always have a 'progression' key (null if no history)."""
        summary = generate_session_summary(winton_race_data, winton_file_info, winton_track_map)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = write_session_summary(summary, tmpdir)
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            assert 'progression' in loaded
