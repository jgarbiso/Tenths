"""Regression: iRacing L/M/R tyre channels are edges seen from behind the car.

On left-side tyres the left edge is the OUTER edge. Tenths used to label tempL
as inner on every tyre, which swapped inner/outer on LF and LR.
"""

import pandas as pd
import pytest

from tenths.analyzer import LOAD_LAT_G, _extract_tire_temps, tire_temp_analysis
from tenths.tyres import inner_middle_outer

HOT, MID, COOL = 90.0, 85.0, 80.0


def _frame(n=200):
    """One loaded lap where every tyre's LEFT edge is the hot one."""
    data = {
        "Lap": [1] * n,
        "LatAccel": [LOAD_LAT_G * 2] * n,
        "LongAccel": [0.0] * n,
    }
    for corner in ("LF", "RF", "LR", "RR"):
        data[f"{corner}tempL"] = [HOT] * n
        data[f"{corner}tempM"] = [MID] * n
        data[f"{corner}tempR"] = [COOL] * n
    return pd.DataFrame(data)


@pytest.mark.parametrize("corner", ["LF", "LR"])
def test_left_edge_is_outer_on_left_tyres(corner):
    t = _extract_tire_temps(_frame(), 1)[corner]
    assert t["outer"] == pytest.approx(HOT)
    assert t["inner"] == pytest.approx(COOL)
    assert t["mid"] == pytest.approx(MID)


@pytest.mark.parametrize("corner", ["RF", "RR"])
def test_left_edge_is_inner_on_right_tyres(corner):
    t = _extract_tire_temps(_frame(), 1)[corner]
    assert t["inner"] == pytest.approx(HOT)
    assert t["outer"] == pytest.approx(COOL)


def test_avg_unchanged_by_orientation():
    temps = _extract_tire_temps(_frame(), 1)
    for t in temps.values():
        assert t["avg"] == pytest.approx((HOT + MID + COOL) / 3)


def test_helper_mapping():
    assert inner_middle_outer("LF", 1, 2, 3) == (3, 2, 1)
    assert inner_middle_outer("LR", 1, 2, 3) == (3, 2, 1)
    assert inner_middle_outer("RF", 1, 2, 3) == (1, 2, 3)
    assert inner_middle_outer("RR", 1, 2, 3) == (1, 2, 3)


def test_legacy_print_uses_same_orientation(capsys):
    tire_temp_analysis(_frame(), 1)
    rows = {line.split()[0]: line.split()[1:] for line in capsys.readouterr().out.splitlines()
            if line.strip()[:2] in ("LF", "RF", "LR", "RR")}
    # Columns are Inner, Mid, Outer, Avg in °F; the hot edge is outer on LF.
    lf_inner, _, lf_outer, _ = (float(v) for v in rows["LF"])
    rf_inner, _, rf_outer, _ = (float(v) for v in rows["RF"])
    assert lf_outer > lf_inner
    assert rf_inner > rf_outer
