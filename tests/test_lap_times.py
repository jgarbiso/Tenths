"""
Lap-time attribution (TECH_DEBT A5).

iRacing publishes a lap's time in LapLastLapTime ~1-2 s after the Lap counter
increments, so the last sample of lap N still holds lap N-1's time. Reading it
there labelled every lap with its predecessor's time and made best_lap select
the lap AFTER the real best. These tests pin the corrected attribution.
"""

import pandas as pd
import pytest

from tenths.analyzer import get_valid_laps, lap_times

DELAY = 100  # samples between the Lap increment and the LapLastLapTime update


def _session(true_times, delay=DELAY, samples_per_lap=500, tail=None):
    """Build a Lap / LapLastLapTime / LapCurrentLapTime frame the way iRacing
    writes it: lap k's time appears `delay` samples into lap k+1.

    true_times: {lap: seconds}, laps in driving order. `tail` adds a final lap of
    that many samples that never completes (the in-lap / session end).
    """
    laps = list(true_times)
    if tail:
        laps.append(laps[-1] + 1)
    rows = []
    held = 0.0
    publish = {}  # sample index -> value
    idx = 0
    for lap in laps:
        n = tail if (tail and lap == laps[-1]) else samples_per_lap
        t_lap = true_times.get(lap, n / 60.0)
        for i in range(n):
            held = publish.get(idx, held)
            rows.append({'Lap': lap, 'LapLastLapTime': held,
                         # Final sample reads ~the published time, as in real files.
                         'LapCurrentLapTime': t_lap * (i + 1) / n})
            idx += 1
        if lap in true_times:
            publish[idx + delay] = true_times[lap]
    return pd.DataFrame(rows)


class TestLapTimes:
    def test_each_lap_gets_its_own_time_not_the_previous(self):
        # Road Atlanta 2026-09-25: the old code reported lap 4 = 82.12 (lap 3's)
        truth = {1: 88.288, 2: 83.781, 3: 82.125, 4: 92.136, 5: 82.462, 6: 82.237}
        times = lap_times(_session(truth, tail=300))
        for lap, t in truth.items():
            assert times[lap] == pytest.approx(t, abs=1e-4), lap

    def test_best_lap_is_the_fast_lap_not_the_one_after(self):
        truth = {1: 88.288, 2: 83.781, 3: 82.125, 4: 92.136, 5: 82.462}
        times = lap_times(_session(truth, tail=300))
        assert min(truth, key=times.get) == 3  # the partial tail lap is not a candidate

    def test_final_lap_without_published_time_uses_current_lap_time(self):
        # Session ends before LapLastLapTime updates for the last lap.
        truth = {1: 90.0, 2: 91.5}
        times = lap_times(_session(truth, delay=10_000))
        assert times[2] == pytest.approx(91.5, abs=1e-6)

    def test_equal_consecutive_times_are_kept(self):
        # No change in LapLastLapTime because both laps ran the same time.
        truth = {1: 90.0, 2: 90.0, 3: 91.0}
        times = lap_times(_session(truth, tail=300))
        assert times[2] == pytest.approx(90.0)

    def test_publish_is_searched_only_in_the_following_lap(self):
        # Lap 1's update never arrives; lap 2 is short and its update lands in
        # lap 3. An unbounded search would give lap 1 lap 2's time (50.0).
        rows = ([{'Lap': 1, 'LapLastLapTime': 0.0, 'LapCurrentLapTime': 9.0 * (i + 1)}
                 for i in range(10)]
                + [{'Lap': 2, 'LapLastLapTime': 0.0, 'LapCurrentLapTime': 50.0}] * 3
                + [{'Lap': 3, 'LapLastLapTime': 0.0, 'LapCurrentLapTime': 1.0}] * 2
                + [{'Lap': 3, 'LapLastLapTime': 50.0, 'LapCurrentLapTime': 2.0}] * 5)
        times = lap_times(pd.DataFrame(rows))
        assert times[1] == pytest.approx(90.0)  # LapCurrentLapTime fallback
        assert times[2] == pytest.approx(50.0)

    def test_single_sample_lap_glitch_does_not_break_attribution(self):
        # iRacing can flip Lap to 0 for one sample on a reset (seen at Road
        # Atlanta). The lap still ends at its LAST sample.
        df = _session({1: 88.0, 2: 83.0}, tail=300)
        glitch = df.index[df['Lap'] == 3][200]  # after lap 2's publish
        df.loc[glitch, 'Lap'] = 0
        times = lap_times(df)
        assert times[1] == pytest.approx(88.0)
        assert times[2] == pytest.approx(83.0)

    def test_no_time_channels(self):
        assert lap_times(pd.DataFrame({'Lap': [1, 1, 2]})) == {}


class TestFirstFlyingLapIsValid:
    """The first timed lap ended with LapLastLapTime still 0 and was dropped."""

    def test_first_lap_passes_the_lap_time_rule(self):
        truth = {1: 88.288, 2: 83.781, 3: 82.125}
        df = _session(truth, samples_per_lap=600, tail=300)
        per_lap = df.groupby('Lap').cumcount()
        sizes = df.groupby('Lap')['Lap'].transform('size')
        df['LapDistPct'] = per_lap / sizes * 100.0
        df['Speed'] = 40.0
        assert df.loc[df['Lap'] == 1, 'LapLastLapTime'].iloc[-1] == 0.0
        assert get_valid_laps(df) == [1, 2, 3]
