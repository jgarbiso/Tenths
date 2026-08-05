"""
End-to-end pipeline tests against a synthetic .ibt.

These run on any machine, including CI, and assert against exact ground truth
rather than the loose ranges the real-.ibt tests are limited to. The synthetic
session has three corners driven identically every lap and one deliberately
inconsistent corner, so the analyser must attribute time loss to that corner
and report none for the others.

Covers what the archive-dependent tests could not verify off the dev machine:
.ibt parsing, lap validity, lap timing, braking-zone detection, apex/min-speed
metrics, corner variance, session summary and HTML report generation.
"""

import json

import pytest

from synthetic_ibt import INCONSISTENT_APEX_SPEEDS_MPS, INCONSISTENT_CORNER_INDEX

MPH_PER_MPS = 2.237


def _apex_mph(data):
    """apex_consistency converted from the analyzer's SI storage to mph.

    Ground truth here is in m/s and the assertions below express tolerances in
    mph, so the actual values are converted rather than the expectations.
    """
    from unit_helpers import apex_results_to_mph
    return apex_results_to_mph(data["apex_consistency"])
SYNTHETIC_APEX_SPEEDS_MPS = INCONSISTENT_APEX_SPEEDS_MPS
INCONSISTENT_CORNER = INCONSISTENT_CORNER_INDEX


class TestIbtParsing:
    """The synthetic file must be a valid .ibt as far as pyirsdk is concerned."""

    def test_pyirsdk_opens_the_file(self, synthetic_session):
        import irsdk
        ibt = irsdk.IBT()
        ibt.open(synthetic_session["path"])
        try:
            assert ibt._disk_header.session_record_count == synthetic_session["sample_count"]
            assert ibt._header.tick_rate == synthetic_session["tick_rate"]
            assert "Speed" in ibt.var_headers_names
            assert len(ibt.get_all("Speed")) == synthetic_session["sample_count"]
        finally:
            ibt.close()

    def test_session_info_parsed(self, synthetic_session):
        from tenths.analyzer import parse_session_info
        si = parse_session_info(synthetic_session["path"])
        assert si["car_screen_name"] == "Ferrari 296 GT3"
        assert si["track_display_name"] == "Test Circuit"
        assert si["event_type"] == "Race"
        assert si["driver_id"] == 999001
        assert si["subsession_id"] == 87654321

    def test_car_class_metadata_available(self, synthetic_session):
        """Metadata exposes the real class — see RR-008, which does not use it."""
        from tenths.analyzer import parse_session_info
        si = parse_session_info(synthetic_session["path"])
        assert si["car_class_short"] == "GT3 Class"

    def test_sample_rate_derived_from_file(self, synthetic_data, synthetic_session):
        assert synthetic_data["sample_rate"] == synthetic_session["tick_rate"]


class TestLapDetectionGroundTruth:
    """Lap validity and timing must match exactly what was written."""

    def test_valid_laps_exactly_match(self, synthetic_data, synthetic_session):
        assert synthetic_data["valid_laps"] == synthetic_session["valid_laps"]

    def test_partial_laps_rejected(self, synthetic_data, synthetic_session):
        """The out-lap and in-lap must not be treated as valid."""
        assert 1 not in synthetic_data["valid_laps"]
        assert max(synthetic_data["valid_laps"]) < 8

    def test_best_lap_identified(self, synthetic_data, synthetic_session):
        assert synthetic_data["best_lap"] == synthetic_session["best_lap"]

    def test_lap_times_match_to_the_millisecond(self, synthetic_data, synthetic_session):
        truth = synthetic_session["lap_times"]
        for result in synthetic_data["lap_results"]:
            assert result["lap"] in truth
            assert result["time"] == pytest.approx(truth[result["lap"]], abs=0.001)

    def test_track_length_recovered(self, synthetic_data, synthetic_session):
        assert synthetic_data["track_length_m"] == pytest.approx(
            synthetic_session["track_length_m"], rel=0.02)


class TestBrakingZoneDetection:
    """One braking zone per corner, in track order."""

    def test_one_zone_per_corner(self, synthetic_data, synthetic_session):
        assert len(synthetic_data["braking_zones"]) == len(synthetic_session["corners"])

    def test_zones_in_track_order(self, synthetic_data):
        pcts = [z["pct"] for z in synthetic_data["braking_zones"]]
        assert pcts == sorted(pcts)

    def test_zone_precedes_its_apex(self, synthetic_data, synthetic_session):
        """The braking zone centre must sit before the apex it serves."""
        for zone, corner in zip(synthetic_data["braking_zones"], synthetic_session["corners"]):
            assert zone["pct"] < corner.pct * 100


class TestMinSpeedGroundTruth:
    """Apex/min-speed metrics must reproduce the configured speeds."""

    def test_consistent_corners_report_zero_spread(self, synthetic_data):
        for i, apex in enumerate(synthetic_data["apex_consistency"]):
            if i == INCONSISTENT_CORNER:
                continue
            assert apex["min_speed_spread_mph"] == pytest.approx(0.0, abs=0.3), (
                f"corner {i} was driven identically every lap but reports "
                f"{apex['min_speed_spread_mph']}mph spread")

    def test_consistent_corners_report_no_over_slowing(self, synthetic_data):
        for i, apex in enumerate(synthetic_data["apex_consistency"]):
            if i == INCONSISTENT_CORNER:
                continue
            assert abs(apex["over_braking_mph"]) < 0.5

    def test_inconsistent_corner_spread_matches_configuration(self, synthetic_data):
        """Spread must equal the configured fastest-minus-slowest apex speed."""
        apex = _apex_mph(synthetic_data)[INCONSISTENT_CORNER]
        expected = (max(SYNTHETIC_APEX_SPEEDS_MPS) - min(SYNTHETIC_APEX_SPEEDS_MPS)) * MPH_PER_MPS
        assert apex["min_speed_spread_mph"] == pytest.approx(expected, abs=1.0)

    def test_best_lap_apex_speed_matches_configuration(self, synthetic_data, synthetic_session):
        """min_speed_best_mph must be the apex speed actually driven on the best lap."""
        best_lap = synthetic_session["best_lap"]
        expected_mps = synthetic_session["apex_speeds"][best_lap][INCONSISTENT_CORNER]
        apex = _apex_mph(synthetic_data)[INCONSISTENT_CORNER]
        assert apex["min_speed_best_mph"] == pytest.approx(expected_mps * MPH_PER_MPS, abs=1.0)

    def test_slowest_lap_reported_as_worst(self, synthetic_data):
        apex = _apex_mph(synthetic_data)[INCONSISTENT_CORNER]
        expected = min(SYNTHETIC_APEX_SPEEDS_MPS) * MPH_PER_MPS
        assert apex["min_speed_worst_mph"] == pytest.approx(expected, abs=1.0)

    def test_apex_speeds_are_corner_specific(self, synthetic_data, synthetic_session):
        """Each corner must report its own apex speed, not a neighbour's."""
        for i, (apex, corner) in enumerate(
                zip(_apex_mph(synthetic_data), synthetic_session["corners"])):
            if i == INCONSISTENT_CORNER:
                continue
            expected = corner.apex_speed_for(0) * MPH_PER_MPS
            assert apex["min_speed_best_mph"] == pytest.approx(expected, abs=1.5), (
                f"corner {i} expected ~{expected:.1f}mph, got {apex['min_speed_best_mph']}")


class TestTimeLossAttributionGroundTruth:
    """The headline claim: time loss lands on the corner that caused it."""

    def _loss_by_pct(self, data):
        return {round(cv["pct"], 1): cv["loss"] for cv in data["corner_variance"]}

    def test_only_the_inconsistent_corner_loses_time(self, synthetic_data, synthetic_session):
        zones = synthetic_data["braking_zones"]
        target_pct = round(zones[INCONSISTENT_CORNER]["pct"], 1)
        losses = self._loss_by_pct(synthetic_data)
        for pct, loss in losses.items():
            if pct == target_pct:
                assert loss > 0.05, "the inconsistent corner should show real loss"
            else:
                assert abs(loss) < 0.05, (
                    f"corner at {pct}% was driven identically but shows {loss:.3f}s loss")

    def test_inconsistent_corner_ranks_first(self, synthetic_data):
        ranked = sorted(synthetic_data["corner_variance"], key=lambda c: -c["loss"])
        zones = synthetic_data["braking_zones"]
        assert round(ranked[0]["pct"], 1) == round(zones[INCONSISTENT_CORNER]["pct"], 1)

    def test_total_recoverable_is_not_double_counted(self, synthetic_data):
        """Sum of losses must be dominated by the single bad corner."""
        total = sum(cv["loss"] for cv in synthetic_data["corner_variance"])
        worst = max(cv["loss"] for cv in synthetic_data["corner_variance"])
        assert total == pytest.approx(worst, abs=0.15)


class TestSampleRateIndependence:
    """A file recorded at a different rate must still time laps correctly."""

    def test_lap_times_correct_at_120hz(self, tmp_path):
        from synthetic_ibt import build_ibt, Corner
        from tenths.analyzer import analyze

        path = tmp_path / "fastcar_testcircuit 2026-07-29 21-00-00.ibt"
        truth = build_ibt(str(path), [Corner(pct=0.3, apex_speeds=25.0),
                                     Corner(pct=0.7, apex_speeds=30.0)],
                          laps=4, track_length_m=1500.0, tick_rate=120)
        data = analyze(str(path))
        assert data is not None
        assert data["sample_rate"] == 120
        for result in data["lap_results"]:
            assert result["time"] == pytest.approx(truth["lap_times"][result["lap"]], abs=0.002)

    def test_reported_loss_is_seconds_not_samples(self, tmp_path):
        """At 120Hz a sample-count bug would double every reported loss."""
        from synthetic_ibt import build_ibt, Corner
        from tenths.analyzer import analyze

        path = tmp_path / "fastcar_testcircuit 2026-07-29 21-30-00.ibt"
        build_ibt(str(path), [Corner(pct=0.3, apex_speeds=[20.0, 26.0, 22.0, 25.0]),
                              Corner(pct=0.7, apex_speeds=30.0)],
                  laps=4, track_length_m=1500.0, tick_rate=120)
        data = analyze(str(path))
        # A 1.5km lap at 120Hz: sector losses are fractions of a second, not tens
        for cv in data["corner_variance"]:
            assert abs(cv["loss"]) < 3.0, f"loss {cv['loss']}s looks like a rate error"


class TestOutputGenerationFromSynthetic:
    """Summary and report generation must work end to end without real telemetry."""

    def test_session_summary_generates(self, synthetic_data, synthetic_file_info):
        from tenths.summary import generate_session_summary
        summary = generate_session_summary(synthetic_data, synthetic_file_info, None)
        assert summary["schema_version"]
        assert summary["best_lap"]["time_seconds"] > 0
        assert len(summary["braking_zones"]) == len(synthetic_data["braking_zones"])
        assert summary["total_valid_laps"] == len(synthetic_data["valid_laps"])

    def test_summary_is_json_serializable(self, synthetic_data, synthetic_file_info):
        from tenths.summary import generate_session_summary
        summary = generate_session_summary(synthetic_data, synthetic_file_info, None)
        reloaded = json.loads(json.dumps(summary, default=str))
        assert reloaded["best_lap"]["time_formatted"]

    def test_summary_written_to_disk(self, synthetic_data, synthetic_file_info, tmp_path):
        from tenths.summary import generate_session_summary, write_session_summary
        summary = generate_session_summary(synthetic_data, synthetic_file_info, None)
        path = write_session_summary(summary, str(tmp_path))
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert "progression" in loaded
        assert loaded["braking_zones"]

    def test_html_report_generates(self, synthetic_data, synthetic_file_info):
        from tenths.report import generate_report
        html = generate_report(synthetic_data, synthetic_file_info, None)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "const DATA =" in html

    def test_report_contains_min_speed_fields(self, synthetic_data, synthetic_file_info):
        from tenths.report import generate_report
        html = generate_report(synthetic_data, synthetic_file_info, None)
        assert "min_speed_spread_mph" in html
        assert "over_braking_mph" in html

    def test_markdown_notes_generate(self, synthetic_data, synthetic_file_info):
        from tenths.process import generate_day_notes
        notes = generate_day_notes(
            [(synthetic_file_info, synthetic_data, None)],
            synthetic_file_info["car"], synthetic_file_info["track"],
            synthetic_file_info["date"], None, None)
        assert "Braking Zones" in notes
        assert "Corner Variance" in notes


class TestQualcommRegression:
    """Portable regression test for the 2026-07-28 corner-attribution bug.

    Reproduces the conditions that produced a false "8.5mph over-slowing at T6"
    on a real race: a long lap with corners only a few percent apart, driven
    identically every lap. Any spread or over-slowing here is attribution error.
    """

    @pytest.fixture(scope="class")
    def qualcomm_data(self, tmp_path_factory):
        from synthetic_ibt import build_ibt, qualcomm_like_corners
        from tenths.analyzer import analyze

        path = tmp_path_factory.mktemp("qualcomm") / "testcar_qualcomm 2026-07-29 20-00-00.ibt"
        truth = build_ibt(str(path), qualcomm_like_corners(), laps=6, track_length_m=5409.0)
        data = analyze(str(path))
        assert data is not None
        return data, truth

    def test_one_zone_per_corner_when_closely_spaced(self, qualcomm_data):
        data, truth = qualcomm_data
        assert len(data["braking_zones"]) == len(truth["corners"])

    def test_no_false_spread_on_identical_laps(self, qualcomm_data):
        """Every corner was driven identically, so spread must be ~zero."""
        data, _ = qualcomm_data
        offenders = {
            i: a["min_speed_spread_mph"]
            for i, a in enumerate(data["apex_consistency"])
            if a["min_speed_spread_mph"] is not None and a["min_speed_spread_mph"] > 2.0
        }
        assert not offenders, f"identical laps reported spread at corners {offenders}"

    def test_no_false_over_slowing_on_identical_laps(self, qualcomm_data):
        data, _ = qualcomm_data
        offenders = {
            i: a["over_braking_mph"]
            for i, a in enumerate(data["apex_consistency"])
            if a["over_braking_mph"] is not None and abs(a["over_braking_mph"]) > 2.0
        }
        assert not offenders, f"identical laps reported over-slowing at corners {offenders}"

    def test_apex_speeds_are_not_a_neighbours(self, qualcomm_data):
        """Each corner must report its own configured apex speed."""
        data, truth = qualcomm_data
        for i, (apex, corner) in enumerate(zip(_apex_mph(data), truth["corners"])):
            expected = corner.apex_speed_for(0) * MPH_PER_MPS
            assert apex["min_speed_best_mph"] == pytest.approx(expected, abs=3.0), (
                f"corner {i} expected ~{expected:.1f}mph, "
                f"got {apex['min_speed_best_mph']} — window sampled the wrong track")

    def test_no_false_time_loss_on_identical_laps(self, qualcomm_data):
        data, _ = qualcomm_data
        for cv in data["corner_variance"]:
            assert abs(cv["loss"]) < 0.1, (
                f"identical laps reported {cv['loss']:.3f}s loss at {cv['pct']:.1f}%")

    def test_an_isolated_off_does_not_become_over_slowing(self, tmp_path):
        """A single slow moment between corners must not be blamed on a corner.

        This is the exact defect: on the real lap a 21.9mph coast 114m past T6
        was reported as 8.5mph of over-slowing at T6.
        """
        from synthetic_ibt import build_ibt, qualcomm_like_corners, Corner
        from tenths.analyzer import analyze

        corners = qualcomm_like_corners()
        # Lap index 5 crawls through what is otherwise a flat-out section
        corners.append(Corner(pct=0.62, apex_speeds=[60.0, 60.0, 60.0, 60.0, 60.0, 10.0],
                              brake_distance_m=60.0, accel_distance_m=80.0))
        path = tmp_path / "testcar_qualcomm 2026-07-29 21-00-00.ibt"
        build_ibt(str(path), corners, laps=6, track_length_m=5409.0)
        data = analyze(str(path))
        assert data is not None

        # The eight real corners must remain clean despite the one-off incident
        for i, a in enumerate(data["apex_consistency"][:len(qualcomm_like_corners())]):
            if a["over_braking_mph"] is None:
                continue
            assert a["over_braking_mph"] < 8.0, (
                f"corner {i} falsely flagged as over-slowing "
                f"({a['over_braking_mph']}mph) by an unrelated slow moment")
