"""
Accuracy tests for the time-loss foundation and corner attribution.

These guard the defects found auditing the 2026-07-28 Qualcomm race:
- apex search windows were ~700m wide on a 5.4km track, so a slow moment
  hundreds of metres away was reported as over-braking at a corner
- the min-speed average included outliers the band had already rejected
- corner sectors overlapped, double-counting summed "recoverable" time
- the sector sample rate was hardcoded to 60Hz
"""

import inspect

import numpy as np
import pandas as pd
import pytest

from tenths.analyzer import (
    _apex_window,
    _corner_sectors,
    _extract_apex_consistency,
    _extract_corner_variance,
    APEX_WINDOW_METERS,
)

MPS_PER_MPH = 1 / 2.237


class TestApexIsLocatedNotAssumed:
    """The apex sits after the braking zone; the window must follow it."""

    def _lap_df(self, lap, brake_center, apex_pct, apex_mph=40.0, entry_mph=120.0):
        rows = []
        for pct in np.arange(brake_center - 4, apex_pct + 6, 0.25):
            # Speed falls linearly to the apex then recovers
            if pct <= apex_pct:
                frac = (pct - (brake_center - 4)) / max(0.01, apex_pct - (brake_center - 4))
                mph = entry_mph - (entry_mph - apex_mph) * frac
            else:
                mph = apex_mph + (pct - apex_pct) * 8
            rows.append({'Lap': lap, 'LapDistPct': float(pct), 'Speed': mph * MPS_PER_MPH})
        return rows

    def test_apex_found_downstream_of_braking_zone(self):
        """Apex located ~2% after the braking centre, as on a real lap."""
        from tenths.analyzer import _apex_reference_pcts
        df = pd.DataFrame(self._lap_df(1, brake_center=46.8, apex_pct=48.5))
        apex = _apex_reference_pcts(df, 1, [46.8], track_length_m=5409)
        assert apex[0] == pytest.approx(48.5, abs=0.3), (
            f"apex located at {apex[0]}, expected ~48.5 (downstream of braking)")

    def test_window_captures_the_apex_speed(self):
        """The window must contain the real minimum, not entry speed."""
        rows = []
        for lap in (1, 2, 3, 4, 5):
            rows += self._lap_df(lap, brake_center=46.8, apex_pct=48.5, apex_mph=40.0 + lap)
        df = pd.DataFrame(rows)
        zone = _extract_apex_consistency(df, [1, 2, 3, 4, 5], [{'pct': 46.8}],
                                        best_lap=1, track_length_m=5409)[0]
        # Apex speeds are 41..45mph; a mis-centred window would report ~100mph+
        assert 38 < zone['avg_apex_mph'] < 50, (
            f"avg {zone['avg_apex_mph']}mph suggests the window missed the apex")

    def test_apex_search_stops_at_next_corner(self):
        from tenths.analyzer import _apex_reference_pcts
        rows = self._lap_df(1, brake_center=20.0, apex_pct=22.0)
        # A much slower point belonging to the NEXT corner
        rows.append({'Lap': 1, 'LapDistPct': 30.0, 'Speed': 5.0 * MPS_PER_MPH})
        df = pd.DataFrame(rows)
        apex = _apex_reference_pcts(df, 1, [20.0, 30.0], track_length_m=5409)
        assert apex[0] < 30.0, "apex search leaked into the next corner"


class TestApexWindowIsCornerSpecific:
    """The apex window must describe the corner, not half the lap."""

    def test_window_scales_with_track_length(self):
        """A fixed metre window is a smaller % of a longer lap."""
        short_lo, short_hi = _apex_window([50.0], 0, track_length_m=2000)
        long_lo, long_hi = _apex_window([50.0], 0, track_length_m=7000)
        assert (short_hi - short_lo) > (long_hi - long_lo)

    def test_long_track_window_is_narrow(self):
        """On a 5.4km circuit the window must be far tighter than the old 13%."""
        lo, hi = _apex_window([46.8], 0, track_length_m=5409)
        assert (hi - lo) < 5.0, f"window {hi - lo:.1f}% is too wide to be corner-specific"

    def test_window_matches_requested_distance(self):
        """Window half-width should reflect APEX_WINDOW_METERS where not clamped."""
        track = 5409.0
        lo, hi = _apex_window([50.0], 0, track_length_m=track)
        expected_half = (APEX_WINDOW_METERS / track) * 100.0
        assert (hi - lo) / 2 == pytest.approx(expected_half, abs=0.01)

    def test_adjacent_corners_cannot_share_track(self):
        """Windows for neighbouring corners must not overlap."""
        centers = [11.7, 18.1, 32.4, 46.8, 55.5, 69.4, 78.3, 89.0]
        windows = [_apex_window(centers, i, 5409) for i in range(len(centers))]
        for i in range(len(windows) - 1):
            assert windows[i][1] <= windows[i + 1][0] + 1e-9, (
                f"corner {i} window {windows[i]} overlaps corner {i+1} {windows[i+1]}")

    def test_window_contains_its_own_centre(self):
        centers = [11.7, 18.1, 32.4]
        for i, c in enumerate(centers):
            lo, hi = _apex_window(centers, i, 5409)
            assert lo <= c <= hi

    def test_duplicate_zones_do_not_collapse_window(self):
        """Near-identical zone centres must still yield a usable window."""
        lo, hi = _apex_window([46.8, 46.9], 0, 5409)
        assert hi > lo


class TestOutlierNotCountedTwice:
    """A value rejected from the band must not still drag the average."""

    def _df(self, speeds, zone_pct=50.0):
        rows = []
        for lap, mph in speeds.items():
            for pct in np.arange(zone_pct - 3, zone_pct + 3.5, 0.5):
                rows.append({'Lap': lap, 'LapDistPct': float(pct),
                             'Speed': 150.0 * MPS_PER_MPH})
            rows.append({'Lap': lap, 'LapDistPct': zone_pct, 'Speed': mph * MPS_PER_MPH})
        return pd.DataFrame(rows)

    def test_average_excludes_rejected_outlier(self):
        """This is the Qualcomm T6 case: one 21.9mph coast must not set the mean."""
        speeds = {1: 53.8, 2: 58.5, 3: 48.1, 4: 56.5, 5: 50.0, 6: 21.9, 7: 51.2, 8: 55.1, 9: 55.1}
        df = self._df(speeds)
        zone = _extract_apex_consistency(df, list(speeds), [{'pct': 50.0}],
                                         best_lap=2, track_length_m=5409)[0]
        untrimmed_mean = float(np.mean(list(speeds.values())))  # ~50.0
        assert zone['avg_apex_mph'] > untrimmed_mean + 2, (
            "average still contaminated by the rejected outlier")
        # best lap 58.5 vs a trimmed mean of ~53.5 -> well under the 8mph trigger
        assert zone['over_braking_mph'] < 8, (
            f"over_braking {zone['over_braking_mph']} would falsely flag over-slowing")

    def test_true_slowest_lap_still_reported(self):
        speeds = {1: 53.8, 2: 58.5, 3: 48.1, 4: 56.5, 5: 50.0, 6: 21.9, 7: 51.2, 8: 55.1, 9: 55.1}
        df = self._df(speeds)
        zone = _extract_apex_consistency(df, list(speeds), [{'pct': 50.0}],
                                         best_lap=2, track_length_m=5409)[0]
        assert zone['min_speed_worst_mph'] == pytest.approx(21.9, abs=0.5)

    def test_genuine_over_slowing_still_detected(self):
        """Trimming must not mask a real, repeated speed deficit."""
        speeds = {1: 70.0, 2: 90.0, 3: 71.0, 4: 69.0, 5: 70.5, 6: 71.5, 7: 70.0}
        df = self._df(speeds)
        zone = _extract_apex_consistency(df, list(speeds), [{'pct': 50.0}],
                                         best_lap=2, track_length_m=5409)[0]
        assert zone['over_braking_mph'] > 8


class TestCornerSectorsNonOverlapping:
    """Summed per-corner losses must not double-count track."""

    def test_qualcomm_sectors_do_not_overlap(self):
        centers = [11.7, 18.1, 32.4, 46.8, 55.5, 69.4, 78.3, 89.0]
        sectors = _corner_sectors(centers)
        assert len(sectors) == len(centers)
        for i in range(len(sectors) - 1):
            assert sectors[i][1] <= sectors[i + 1][0] + 1e-9, (
                f"sector {i} ends {sectors[i][1]} after sector {i+1} starts {sectors[i+1][0]}")

    def test_widely_spaced_corners_keep_full_window(self):
        """With room to spare, the original -3/+8 shape is preserved."""
        sectors = _corner_sectors([20.0, 60.0])
        assert sectors[0][0] == pytest.approx(17.0)
        assert sectors[0][1] == pytest.approx(28.0)

    def test_total_span_never_exceeds_lap(self):
        centers = [5.0, 9.0, 14.0, 20.0, 27.0, 35.0, 44.0, 54.0, 65.0, 77.0, 90.0]
        sectors = _corner_sectors(centers)
        assert sum(e - s for s, e, _ in sectors) <= 100.0

    def test_each_sector_contains_its_centre(self):
        centers = [11.7, 18.1, 32.4, 46.8]
        for s, e, c in _corner_sectors(centers):
            assert s <= c <= e


class TestSampleRateNotHardcoded:
    """Sector timing must use the rate derived from the file."""

    def test_corner_variance_accepts_sample_rate(self):
        sig = inspect.signature(_extract_corner_variance)
        assert 'sample_rate' in sig.parameters

    def _lap_df(self, laps, samples_per_lap, rate_marker=1.0):
        rows = []
        for lap in laps:
            n = samples_per_lap[lap]
            for i in range(n):
                pct = (i / n) * 100.0
                rows.append({
                    'Lap': lap,
                    'LapDistPct': pct,
                    'Speed': 40.0,
                    'Brake': 80.0 if 18.0 <= pct <= 22.0 else 0.0,
                    'LapLastLapTime': 100.0 + laps.index(lap),
                })
        return pd.DataFrame(rows)

    def test_reported_times_scale_with_rate(self):
        """Doubling the sample rate must not double the reported sector time."""
        laps = [1, 2, 3, 4]
        counts = {1: 600, 2: 640, 3: 620, 4: 660}
        df = self._lap_df(laps, counts)
        at60 = _extract_corner_variance(df, laps, 1, sample_rate=60)
        at120 = _extract_corner_variance(df, laps, 1, sample_rate=120)
        assert at60 and at120
        # Same physical laps, so a correct implementation reports half the time
        # at double the rate — proving the rate is actually applied.
        assert at60[0]['avg'] == pytest.approx(at120[0]['avg'] * 2, rel=1e-6)


class TestZoneSplitIsDistanceBased:
    """Braking zones must split on a real distance gap, not a fixed percentage.

    On the 5409m Qualcomm lap the old fixed 5% threshold (270m) merged T2 and T3
    into a single 384m "corner" and reported their combined time as T2.
    """

    def test_threshold_shrinks_on_longer_tracks(self):
        from tenths.analyzer import _zone_gap_pct
        assert _zone_gap_pct(5409) < _zone_gap_pct(2945)

    def test_threshold_is_the_configured_distance(self):
        from tenths.analyzer import _zone_gap_pct, ZONE_GAP_METERS
        track = 5409.0
        assert _zone_gap_pct(track) == pytest.approx(ZONE_GAP_METERS / track * 100, abs=0.01)

    def test_threshold_clamped_for_extreme_tracks(self):
        from tenths.analyzer import (_zone_gap_pct, ZONE_GAP_MIN_PCT, ZONE_GAP_MAX_PCT)
        assert _zone_gap_pct(50000) == pytest.approx(ZONE_GAP_MIN_PCT)
        assert _zone_gap_pct(500) == pytest.approx(ZONE_GAP_MAX_PCT)

    def test_falls_back_without_track_length(self):
        from tenths.analyzer import _zone_gap_pct, DEFAULT_ZONE_GAP_PCT
        assert _zone_gap_pct(None) == DEFAULT_ZONE_GAP_PCT
        assert _zone_gap_pct(0) == DEFAULT_ZONE_GAP_PCT

    def test_corners_206m_apart_stay_separate_on_a_long_lap(self):
        """The T2/T3 case: a 206m gap must be two zones on a 5409m lap."""
        from tenths.analyzer import _zone_ids
        track = 5409.0
        # Braking samples for two corners separated by 206m (3.8% of the lap)
        first = np.arange(9.1, 11.8, 0.05)
        second = np.arange(15.5, 18.2, 0.05)
        pct = pd.Series(np.concatenate([first, second]))
        ids = _zone_ids(pct, track)
        assert ids.nunique() == 2, "corners 206m apart were merged into one zone"

    def test_same_gap_merges_when_it_is_genuinely_short(self):
        """The same 3.8% gap on a 1200m lap is only 46m — one braking event."""
        from tenths.analyzer import _zone_ids
        first = np.arange(9.1, 11.8, 0.05)
        second = np.arange(15.5, 18.2, 0.05)
        pct = pd.Series(np.concatenate([first, second]))
        assert _zone_ids(pct, 1200.0).nunique() == 1

    def test_continuous_braking_is_one_zone(self):
        from tenths.analyzer import _zone_ids
        pct = pd.Series(np.arange(20.0, 24.0, 0.05))
        assert _zone_ids(pct, 5409.0).nunique() == 1
