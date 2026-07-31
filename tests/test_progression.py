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


class TestNestedPerSessionLayout:
    """RR-003: history must be found in the watcher's car/track/date/time layout.

    compute_progression previously assumed the parent of session_dir was the
    car/track directory and scanned only its direct children. Given a time-level
    folder that meant it searched sibling times under the current date and never
    saw earlier dates, so the first session of each day reported "First Session"
    and no PB check.
    """

    def _write_session(self, track_dir, date, time_label, best_time, abs_hits=30):
        session = os.path.join(track_dir, date, time_label) if time_label \
            else os.path.join(track_dir, date)
        os.makedirs(session, exist_ok=True)
        with open(os.path.join(session, 'session_summary.json'), 'w', encoding='utf-8') as f:
            json.dump({
                'schema_version': '1.0.0',
                'session': {'date': date, 'time': time_label},
                'best_lap': {'time_seconds': best_time},
                'abs': {'cleanest_hits': abs_hits, 'per_lap_totals': [abs_hits]},
                'total_recoverable_time_s': 1.0,
            }, f)
        return session

    def _current(self, date, time_label, best_time):
        return {
            'session': {'date': date, 'time': time_label},
            'best_lap': {'time_seconds': best_time},
            'abs': {'cleanest_hits': 25, 'per_lap_totals': [25]},
            'total_recoverable_time_s': 0.9,
        }

    def test_finds_previous_day_from_time_level_folder(self, tmp_path):
        track = str(tmp_path)
        self._write_session(track, '2026-07-28', '20-57-02', 128.3)
        current = self._write_session(track, '2026-07-29', '21-04-37', 127.4)

        result = compute_progression(self._current('2026-07-29', '21-04-37', 127.4), current)
        assert result is not None, "previous day's session was not found"
        assert result['previous_session']['date'] == '2026-07-28'
        assert result['delta_vs_previous']['lap_time_s'] == pytest.approx(-0.9, abs=0.01)

    def test_does_not_compare_a_session_against_itself(self, tmp_path):
        """Reprocessing must not read the session's own stale summary."""
        track = str(tmp_path)
        current = self._write_session(track, '2026-07-28', '20-57-02', 128.3)
        # Only its own summary exists, so there is no history at all
        result = compute_progression(self._current('2026-07-28', '20-57-02', 128.3), current)
        assert result is None, "session was compared against its own summary"

    def test_orders_multiple_sessions_on_the_same_day(self, tmp_path):
        track = str(tmp_path)
        self._write_session(track, '2026-07-29', '21-04-37', 127.4)
        current = self._write_session(track, '2026-07-29', '22-09-18', 126.7)

        result = compute_progression(self._current('2026-07-29', '22-09-18', 126.7), current)
        assert result is not None
        assert result['previous_session']['time'] == '21-04-37' or \
            result['previous_session']['best_lap_time_s'] == pytest.approx(127.4)
        assert result['session_count'] == 2

    def test_full_history_across_days_and_times(self, tmp_path):
        track = str(tmp_path)
        self._write_session(track, '2026-07-28', '20-57-02', 128.3)
        self._write_session(track, '2026-07-29', '21-04-37', 127.4)
        current = self._write_session(track, '2026-07-29', '22-09-18', 126.7)

        result = compute_progression(self._current('2026-07-29', '22-09-18', 126.7), current)
        assert result['session_count'] == 3
        assert result['trend']['lap_times'] == [128.3, 127.4, 126.7]
        assert result['alltime_best']['is_new_pb'] is True

    def test_pb_detected_across_dates(self, tmp_path):
        track = str(tmp_path)
        self._write_session(track, '2026-07-28', '20-57-02', 126.0)
        current = self._write_session(track, '2026-07-29', '21-04-37', 127.4)

        result = compute_progression(self._current('2026-07-29', '21-04-37', 127.4), current)
        assert result['alltime_best']['is_new_pb'] is False
        assert result['alltime_best']['lap_time_s'] == pytest.approx(126.0)

    def test_corrupt_history_is_skipped_not_fatal(self, tmp_path):
        track = str(tmp_path)
        self._write_session(track, '2026-07-27', '19-00-00', 129.0)
        broken = os.path.join(track, '2026-07-28', '20-00-00')
        os.makedirs(broken)
        with open(os.path.join(broken, 'session_summary.json'), 'w', encoding='utf-8') as f:
            f.write('{ not valid json')
        current = self._write_session(track, '2026-07-29', '21-04-37', 127.4)

        result = compute_progression(self._current('2026-07-29', '21-04-37', 127.4), current)
        assert result is not None, "one corrupt summary discarded all history"
        assert result['session_count'] == 2

    def test_mixed_old_and_new_layouts(self, tmp_path):
        """Date-level output from earlier versions must still count."""
        track = str(tmp_path)
        self._write_session(track, '2026-07-27', '', 129.0)          # old layout
        current = self._write_session(track, '2026-07-29', '21-04-37', 127.4)

        result = compute_progression(self._current('2026-07-29', '21-04-37', 127.4), current)
        assert result is not None
        assert result['session_count'] == 2

    def test_track_dir_resolution(self, tmp_path):
        from tenths.summary import _find_track_dir
        track = str(tmp_path)
        time_level = os.path.join(track, '2026-07-29', '21-04-37')
        os.makedirs(time_level)
        assert os.path.normcase(_find_track_dir(time_level)) == os.path.normcase(track)

        date_level = os.path.join(track, '2026-07-28')
        os.makedirs(date_level, exist_ok=True)
        assert os.path.normcase(_find_track_dir(date_level)) == os.path.normcase(track)

    def test_other_cars_are_not_mixed_in(self, tmp_path):
        """History must be scoped to one car/track tree."""
        car_a = tmp_path / 'carA' / 'track1'
        car_b = tmp_path / 'carB' / 'track1'
        self._write_session(str(car_a), '2026-07-28', '20-00-00', 128.0)
        self._write_session(str(car_b), '2026-07-28', '20-00-00', 100.0)
        current = self._write_session(str(car_a), '2026-07-29', '21-00-00', 127.0)

        result = compute_progression(self._current('2026-07-29', '21-00-00', 127.0), current)
        assert result['session_count'] == 2, "another car's sessions were included"
        assert result['alltime_best']['lap_time_s'] == pytest.approx(127.0)


class TestChronologyAndDuplicates:
    """History must be strictly earlier, and the same session counted once."""

    def _write(self, track_dir, date, time_label, best_time):
        session = os.path.join(track_dir, date, time_label) if time_label \
            else os.path.join(track_dir, date)
        os.makedirs(session, exist_ok=True)
        with open(os.path.join(session, 'session_summary.json'), 'w', encoding='utf-8') as f:
            json.dump({
                'schema_version': '1.0.0',
                'session': {'date': date, 'time': time_label},
                'best_lap': {'time_seconds': best_time},
                'abs': {'cleanest_hits': 20, 'per_lap_totals': [20]},
                'total_recoverable_time_s': 1.0,
            }, f)
        return session

    def _current(self, date, time_label, best_time):
        return {
            'session': {'date': date, 'time': time_label},
            'best_lap': {'time_seconds': best_time},
            'abs': {'cleanest_hits': 20, 'per_lap_totals': [20]},
            'total_recoverable_time_s': 1.0,
        }

    def test_later_session_is_not_treated_as_previous(self, tmp_path):
        """Reprocessing an old session must not compare it against a newer one."""
        track = str(tmp_path)
        current = self._write(track, '2026-07-28', '20-00-00', 128.0)
        self._write(track, '2026-07-29', '21-00-00', 126.0)   # recorded later

        result = compute_progression(self._current('2026-07-28', '20-00-00', 128.0), current)
        assert result is None, "a future session was used as history"

    def test_earlier_session_still_found(self, tmp_path):
        track = str(tmp_path)
        self._write(track, '2026-07-27', '19-00-00', 129.0)
        current = self._write(track, '2026-07-28', '20-00-00', 128.0)
        result = compute_progression(self._current('2026-07-28', '20-00-00', 128.0), current)
        assert result is not None
        assert result['previous_session']['date'] == '2026-07-27'

    def test_same_session_in_two_layouts_counted_once(self, tmp_path):
        """Legacy date-level output of the same session must not double count."""
        track = str(tmp_path)
        # Same session, written by an older version at date level
        self._write(track, '2026-07-28', '', 128.0)
        legacy = os.path.join(track, '2026-07-28', 'session_summary.json')
        with open(legacy, 'r+', encoding='utf-8') as f:
            data = json.load(f)
            data['session']['time'] = '20-57-02'
            f.seek(0)
            json.dump(data, f)
            f.truncate()
        current = self._write(track, '2026-07-28', '20-57-02', 128.0)

        result = compute_progression(self._current('2026-07-28', '20-57-02', 128.0), current)
        assert result is None, "a copy of the same session was used as history"

    def test_duplicate_history_entries_deduplicated(self, tmp_path):
        track = str(tmp_path)
        self._write(track, '2026-07-27', '19-00-00', 129.0)
        # The same earlier session also present at date level
        self._write(track, '2026-07-27', '', 129.0)
        legacy = os.path.join(track, '2026-07-27', 'session_summary.json')
        with open(legacy, 'r+', encoding='utf-8') as f:
            data = json.load(f)
            data['session']['time'] = '19-00-00'
            f.seek(0)
            json.dump(data, f)
            f.truncate()
        current = self._write(track, '2026-07-28', '20-00-00', 128.0)

        result = compute_progression(self._current('2026-07-28', '20-00-00', 128.0), current)
        assert result['session_count'] == 2, "the same session was counted twice"
