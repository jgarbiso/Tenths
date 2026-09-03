"""
Tests for the trail-braking zone diagnosis (analyzer.diagnose_trail_zone).

Regression guarded here: TECH_DEBT A7. The old rule
    yaw > 0.5 and brake > 20  ->  "High yaw — oversteer risk"
fired on 87 of 469 trail zones (19%) measured across 40+ archived sessions and
four car models, and every one was a false positive — an advanced driver
rotating the car on the brake at high lateral G, which is good technique, not
instability (ARA neutral-steer / three-tools-of-rotation, SimCoach/CONTEXT.md).

The values below are taken from that measured distribution. High lateral G with
high yaw must NOT be called oversteer; the only case that keeps the warning is
high yaw with the brake on but WITHOUT cornering load, which is the genuine
rear-stepping-out signature. No such zone appeared on any clean best lap, so
that branch is covered by a synthetic case here rather than real data.

The diagnosis logic was duplicated in two functions with divergent labels
("GOOD" vs "Good"); it now lives once in diagnose_trail_zone and both callers
delegate to it. Source assertions pin that so it cannot drift again.
"""

import inspect

import pytest

from tenths import analyzer
from tenths.analyzer import diagnose_trail_zone


class TestNoFalseOversteerAtHighG:
    """Every real high-G high-yaw zone measured was controlled rotation."""

    # (brake_pct, lateral_g, yaw_rate) drawn from the 87 zones the old rule
    # wrongly flagged. Spans the full measured lat-G range, 1.1 G to 2.9 G.
    HIGH_G_FALSE_POSITIVES = [
        (22, 2.93, 0.68),   # ferrari296gt3 coronado
        (23, 2.68, 0.68),   # watkinsglen T1 — the doc's headline example
        (27, 2.54, 0.80),   # barber
        (24, 2.21, 0.65),   # bmwm4gt3 midohio
        (27, 1.73, 0.75),   # virginia T — old rule fired here
        (34, 1.19, 0.51),   # cota — borderline, must still be loaded
        (33, 1.11, 0.53),   # coronado — borderline, must still be loaded
    ]

    @pytest.mark.parametrize("brk,lat,yaw", HIGH_G_FALSE_POSITIVES)
    def test_high_g_high_yaw_is_not_oversteer(self, brk, lat, yaw):
        diag = diagnose_trail_zone(brk, lat, yaw)
        assert "oversteer" not in diag.lower(), (
            f"brake={brk} lat={lat}G yaw={yaw} is controlled rotation, not "
            f"oversteer, but got: {diag!r}")

    def test_fast_corner_reads_as_high_speed_rotation(self):
        """A clearly fast corner with high yaw gets the positive label."""
        assert diagnose_trail_zone(27, 2.54, 0.80) == (
            "High-speed rotation — normal for this corner speed")


class TestGenuineOversteerStillFlagged:
    """The real signature — high yaw, brake on, but low cornering load — is the
    only case that keeps the warning, so a real spin is not silenced."""

    OVERSTEER = "Oversteer risk — rear rotating beyond corner load"

    def test_low_g_high_yaw_with_brake_flags_oversteer(self):
        assert diagnose_trail_zone(30, 0.7, 0.65) == self.OVERSTEER

    def test_high_yaw_off_brake_is_not_diagnosed_as_trail_oversteer(self):
        """No brake means it is not a trail-braking oversteer case."""
        diag = diagnose_trail_zone(5, 0.6, 0.9)
        assert "oversteer" not in diag.lower()

    def test_spin_under_heavy_braking_is_not_called_braking_straight(self):
        """Ordering guard. "Braking straight" matches on brake>60 + low lat-G,
        which is exactly what a spin under heavy braking looks like. Abnormal
        rotation must be checked first or the spin is silently absorbed."""
        assert diagnose_trail_zone(70, 0.30, 1.20) == self.OVERSTEER

    def test_big_moment_in_the_loaded_band_is_not_called_good(self):
        """Ordering guard. Any zone at/above COMBINED_LOAD_LAT_G is treated as
        loaded, so without the abnormal-rotation check a violent moment just
        above 1.0 G would be reported as "Good — combined load"."""
        assert diagnose_trail_zone(30, 1.05, 1.50) == self.OVERSTEER
        assert diagnose_trail_zone(30, 1.15, 1.30) == self.OVERSTEER

    def test_abnormal_threshold_sits_above_the_measured_clean_lap_ceiling(self):
        """The fastest rotation on any of the 469 measured clean-lap zones was
        1.03 rad/s. That must still read as normal, so the abnormal-rotation
        guard cannot start firing on good driving."""
        diag = diagnose_trail_zone(52, 2.00, 1.03)
        assert "oversteer" not in diag.lower()
        assert analyzer.ABNORMAL_YAW_RATE > 1.03


class TestMissingDataNeverWarns:
    """Non-finite telemetry must not manufacture an oversteer warning. NaN fails
    every comparison, so without an explicit guard it fell through to the
    oversteer branch and reported instability for a zone with no lateral data."""

    @pytest.mark.parametrize("brk,lat,yaw", [
        (30, float("nan"), 0.60),
        (30, 1.50, float("nan")),
        (float("nan"), 1.50, 0.60),
        (30, float("inf"), 0.60),
    ])
    def test_non_finite_inputs_do_not_warn(self, brk, lat, yaw):
        diag = diagnose_trail_zone(brk, lat, yaw)
        assert "oversteer" not in diag.lower(), (
            f"missing/invalid data produced a warning: {diag!r}")


class TestOtherBranches:
    def test_combined_load(self):
        assert diagnose_trail_zone(40, 1.5, 0.3) == "Good — combined load"

    def test_braking_straight(self):
        assert diagnose_trail_zone(70, 0.3, 0.1) == "Braking straight"

    def test_light_trail(self):
        assert diagnose_trail_zone(12, 0.6, 0.2) == "Light trail"


class TestSingleSourceOfTruth:
    """Both trail-zone callers must delegate to diagnose_trail_zone, and neither
    may re-implement the old inline yaw rule."""

    def test_both_callers_delegate(self):
        for name in ("trail_braking_analysis", "_extract_trail_braking"):
            src = inspect.getsource(getattr(analyzer, name))
            assert "diagnose_trail_zone(" in src, (
                f"{name} must call diagnose_trail_zone")

    def test_old_inline_rule_is_gone(self):
        for name in ("trail_braking_analysis", "_extract_trail_braking"):
            src = inspect.getsource(getattr(analyzer, name))
            assert "High yaw" not in src, (
                f"{name} still carries the old inline diagnosis string")
            assert "oversteer risk" not in src.lower(), (
                f"{name} still carries an inline oversteer literal")


class TestSteeringRateDeliberatelyUnused:
    """The earlier spec proposed a yaw/steering-rate ratio. Measurement showed
    steering rate is too noisy at 60 Hz (single-sample spikes of 20-67 rad/s),
    so the diagnosis is built on lateral G instead. Guard that the noisy signal
    was not reintroduced into the classifier."""

    def test_diagnose_signature_has_no_steering_argument(self):
        params = list(inspect.signature(diagnose_trail_zone).parameters)
        assert params == ["brake_pct", "lateral_g", "yaw_rate"], (
            f"diagnose_trail_zone must classify from brake/lat/yaw only, "
            f"got {params}")
