"""
Setup notebook — capture of setups and car behaviour per car/track.

The notebook's value rests on three facts that are easy to get wrong, each
guarded here:
  * in-car settings come from the live dc* channels, not the garage snapshot;
  * lap times come from LapCurrentLapTime, because LapLastLapTime lags the line;
  * the notebook is optional — a failure in it never blocks processing.
"""

import json
import math
import os

import numpy as np
import pandas as pd
import pytest

from tenths import setup_notebook as nb


# ─── Setup extraction ─────────────────────────────────────────────────────────

CAR_SETUP = {
    "UpdateCount": 6,
    "TiresAero": {
        "LeftFront": {"StartingPressure": "159 kPa", "LastHotPressure": "159 kPa",
                      "LastTempsOMI": "35C, 35C, 35C", "TreadRemaining": "100%, 100%, 100%"},
        "AeroBalanceCalc": {"FrontDownforce": "38.9%"},
    },
    "Chassis": {
        "LeftFront": {"Camber": "-4.0 deg", "CornerWeight": "3328 N"},
        "InCarAdjustments": {"BrakePressureBias": "53.0%", "TcSetting": "1 (TC)",
                             "AbsSetting": "4 (ABS)", "DashDisplayPage": "RACE 2"},
    },
}


class TestSetupClassification:
    def test_flatten_uses_dotted_paths(self):
        flat = nb.flatten_setup(CAR_SETUP)
        assert flat["Chassis.LeftFront.Camber"] == "-4.0 deg"

    def test_readings_and_cosmetics_are_not_settings(self):
        settings, computed = nb.classify_setup(nb.flatten_setup(CAR_SETUP))
        every = set(settings) | set(computed)
        for leaf in ("LastHotPressure", "LastTempsOMI", "TreadRemaining",
                     "UpdateCount", "DashDisplayPage"):
            assert not any(k.endswith(leaf) for k in every), leaf

    def test_computed_values_are_kept_apart(self):
        settings, computed = nb.classify_setup(nb.flatten_setup(CAR_SETUP))
        assert "Chassis.LeftFront.CornerWeight" in computed
        assert "TiresAero.AeroBalanceCalc.FrontDownforce" in computed
        assert "Chassis.LeftFront.Camber" in settings
        assert "TiresAero.LeftFront.StartingPressure" in settings


def _laps_frame(per_lap):
    """DataFrame with a Lap column and per-lap constant channel values."""
    rows = []
    for lap, values in per_lap.items():
        for _ in range(10):
            rows.append({"Lap": lap, **values})
    return pd.DataFrame(rows)


class TestInCarSettings:
    def test_live_value_replaces_garage_snapshot(self):
        # Road Atlanta 2026-09-25: garage said TC 1 / ABS 4 / 53.0%, the car ran 4 / 3 / 51.5.
        settings, _ = nb.classify_setup(nb.flatten_setup(CAR_SETUP))
        df = _laps_frame({2: {"dcTractionControl": 4.0, "dcABS": 3.0, "dcBrakeBias": 51.5},
                          3: {"dcTractionControl": 4.0, "dcABS": 3.0, "dcBrakeBias": 51.5}})
        live = nb.in_car_settings(df, [2, 3], settings)
        tc = live["Chassis.InCarAdjustments.TcSetting"]
        assert tc["value"] == 4.0 and tc["garage_value"] == "1 (TC)" and not tc["varied"]
        assert live["Chassis.InCarAdjustments.BrakePressureBias"]["value"] == 51.5

    def test_change_between_laps_is_flagged(self):
        settings, _ = nb.classify_setup(nb.flatten_setup(CAR_SETUP))
        df = _laps_frame({2: {"dcBrakeBias": 53.0}, 3: {"dcBrakeBias": 51.5},
                          4: {"dcBrakeBias": 51.5}})
        live = nb.in_car_settings(df, [2, 3, 4], settings)["Chassis.InCarAdjustments.BrakePressureBias"]
        assert live["varied"] and live["value"] == 51.5
        assert live["per_lap"] == {2: 53.0, 3: 51.5, 4: 51.5}

    def test_missing_channels_are_skipped(self):
        assert nb.in_car_settings(_laps_frame({1: {"Speed": 1.0}}), [1], {}) == {}


# ─── Laps ─────────────────────────────────────────────────────────────────────

class TestLapTimes:
    def test_uses_the_analyzers_lap_times(self):
        # iRacing publishes lap N's time ~1.7 s into lap N+1; the notebook must use
        # analyzer.lap_times, not the value on lap N's last sample.
        df = pd.DataFrame({
            "Lap":               [2, 2, 2, 3, 3, 3, 4],
            "LapCurrentLapTime": [1.0, 50.0, 88.0, 1.0, 40.0, 82.0, 1.0],
            "LapLastLapTime":    [90.0, 90.0, 90.0, 90.0, 88.0, 88.0, 82.0],
        })
        assert nb.session_lap_times(df, [2, 3]) == {2: 88.0, 3: 82.0}

    def test_clean_laps_drop_slow_laps(self):
        times = {2: 83.78, 3: 82.13, 4: 92.13, 5: 82.47, 6: 82.23}
        assert nb.clean_laps(times) == [2, 3, 5, 6]

    def test_clean_laps_empty(self):
        assert nb.clean_laps({}) == []


# ─── Balance ──────────────────────────────────────────────────────────────────

def _arc(n, speed, radius, steer, brake=0.0, throttle=0.0, lat_g=1.5):
    """n samples driving a steady arc; left turn when radius > 0."""
    yaw = speed / radius
    return pd.DataFrame({
        "Speed": [speed] * n, "YawRate": [yaw] * n, "SteeringWheelAngle": [steer] * n,
        "LatAccel": [lat_g] * n, "Brake": [brake] * n, "Throttle": [throttle] * n,
    })


class TestBalanceProfile:
    def test_steer_demand_is_wheel_degrees_for_100m_arc(self):
        # 0.6 rad of lock on a 100 m arc -> 0.6 rad = 34.4 degrees.
        d = _arc(120, speed=35.0, radius=100.0, steer=0.6, throttle=80.0)
        bal = nb.balance_profile(d, n_laps=1)
        assert bal["steer_demand_deg"]["medium"]["exit"] == pytest.approx(
            math.degrees(0.6), abs=0.1)
        assert bal["steer_demand_deg"]["medium"]["entry"] is None   # too few samples

    def test_more_lock_for_same_arc_reads_higher(self):
        low = nb.balance_profile(_arc(120, 50.0, 200.0, 0.3), 1)
        high = nb.balance_profile(_arc(120, 50.0, 200.0, 0.4), 1)
        assert high["steer_demand_deg"]["fast"]["mid"] > low["steer_demand_deg"]["fast"]["mid"]

    def test_right_turns_read_the_same_as_left(self):
        left = nb.balance_profile(_arc(120, 20.0, 60.0, 0.5, brake=40.0), 1)
        right = nb.balance_profile(_arc(120, 20.0, -60.0, -0.5, brake=40.0, lat_g=-1.5), 1)
        assert left["steer_demand_deg"]["slow"]["entry"] == right["steer_demand_deg"]["slow"]["entry"]

    def test_countersteer_counts_events_not_samples(self):
        normal = _arc(60, 20.0, 60.0, 0.5, throttle=80.0)
        catch = _arc(12, 20.0, 60.0, -0.2, throttle=80.0)      # opposite lock, 0.2 s
        blip = _arc(3, 20.0, 60.0, -0.2, throttle=80.0)        # too short to count
        d = pd.concat([normal, catch, normal, blip, normal], ignore_index=True)
        bal = nb.balance_profile(d, n_laps=2)
        assert bal["countersteer_per_lap"] == {"entry": 0.0, "mid": 0.0, "exit": 0.5}

    def test_missing_channels_return_none(self):
        assert nb.balance_profile(pd.DataFrame({"Speed": [1.0]}), 1) is None


# ─── Tyres and platform ───────────────────────────────────────────────────────

class TestTyres:
    def test_left_tyre_left_edge_is_outer(self):
        assert nb._edges("LF", 1, 2, 3) == {"inner": 3, "middle": 2, "outer": 1}
        assert nb._edges("RR", 1, 2, 3) == {"inner": 1, "middle": 2, "outer": 3}

    def test_pit_snapshot_absent_without_a_pit_visit(self):
        df = pd.DataFrame({"LFtempCM": [34.8] * 5})
        assert nb.pit_snapshot(df) is None

    def test_pit_snapshot_takes_last_reading_and_wear(self):
        cols = {f"{c}temp{p}": [35.0, 35.0, 90.0, 35.0] for c in nb.CORNERS
                for p in ("CL", "CM", "CR")}
        cols.update({f"{c}wear{p}": [1.0, 1.0, 0.95, 1.0] for c in nb.CORNERS
                     for p in ("L", "M", "R")})
        snap = nb.pit_snapshot(pd.DataFrame(cols))
        assert snap["carcass_c"]["LF"]["middle"] == 90.0
        assert snap["tread_used_pct"]["RR"]["outer"] == pytest.approx(5.0)

    def test_pressure_still_rising_is_not_stable(self):
        df = _laps_frame({2: {f"{c}pressure": 170.0 for c in nb.CORNERS},
                          3: {f"{c}pressure": 180.0 for c in nb.CORNERS}})
        tires = nb.tire_profile(df, [2, 3], {2: 80.0, 3: 80.0})
        assert tires["pressure_stable"] is False
        assert tires["hot_pressure_kpa"]["LF"] == 180.0


class TestPlatform:
    def test_ride_height_in_mm_and_rake(self):
        n = 200
        d = pd.DataFrame({
            "Speed": [60.0] * n,
            "LFrideHeight": [0.040] * n, "RFrideHeight": [0.040] * n,
            "LRrideHeight": [0.050] * n, "RRrideHeight": [0.050] * n,
        })
        plat = nb.platform_profile(d)
        assert plat["min_ride_height_mm"]["LF"] == 40.0
        assert plat["rake_at_speed_mm"] == 10.0


# ─── Diffs and rendering ──────────────────────────────────────────────────────

def _entry(tc_garage="1 (TC)", tc_driven=4.0, camber="-4.0 deg", recorded="2026-09-25 17:30"):
    key = "Chassis.InCarAdjustments.TcSetting"
    return {
        "id": f"x {recorded}.ibt", "recorded": recorded, "session_types": ["Practice"],
        "car": "Ford Mustang GT3", "track": "Road Atlanta", "track_config": "Full Course",
        "conditions": {"air": "26 C", "track": "29 C"}, "setup_name": "lemans.sto",
        "settings": {key: tc_garage, "Chassis.LeftFront.Camber": camber},
        "computed": {}, "flags": [],
        "in_car": {key: {"value": tc_driven, "garage_value": tc_garage,
                         "varied": False, "per_lap": {"2": tc_driven}}},
        "pace": {"valid_laps": 3, "clean_laps": [2, 3, 4], "measured_laps": [2, 3, 4],
                 "lap_times_s": {"2": 82.1, "3": 82.2, "4": 82.3},
                 "best_s": 82.1, "best_lap": 2, "clean_mean_s": 82.2, "clean_std_s": 0.1},
        "balance": None, "platform": None, "tires": None,
    }


class TestSetupDiff:
    def test_garage_snapshot_change_alone_is_not_a_change(self):
        # Garage TC value moved but the driver ran the same TC: nothing changed.
        assert nb.setup_diff(_entry(tc_garage="1 (TC)"), _entry(tc_garage="2 (TC)")) == []

    def test_driven_change_is_a_change(self):
        diff = nb.setup_diff(_entry(tc_driven=4.0), _entry(tc_driven=3.0))
        assert [d[0] for d in diff] == ["Chassis.InCarAdjustments.TcSetting"]

    def test_garage_setting_change(self):
        diff = nb.setup_diff(_entry(camber="-4.0 deg"), _entry(camber="-3.6 deg"))
        assert diff == [("Chassis.LeftFront.Camber", "-4.0 deg", "-3.6 deg")]


class TestRender:
    def test_markdown_lists_sessions_and_changes(self):
        notebook = {"car": "Ford Mustang GT3", "track": "Road Atlanta",
                    "entries": [_entry(recorded="2026-09-25 17:30"),
                                _entry(camber="-3.6 deg", recorded="2026-09-26 18:00")]}
        md = nb.render_markdown(notebook)
        assert "# Setup notebook — Ford Mustang GT3 at Road Atlanta" in md
        assert "| Chassis.LeftFront.Camber | -4.0 deg | -3.6 deg |" in md
        assert "TcSetting: **4** [1 (TC)]" in md
        # newest session is described first
        assert md.index("### 2. 2026-09-26") < md.index("### 1. 2026-09-25")

    def test_imperial_display_converts_metric_setup_strings(self, monkeypatch):
        # The .ibt setup is always metric; the garage (and Tenths) may be imperial.
        from tenths import config
        monkeypatch.setattr(config, "UNITS", config.UNITS_IMPERIAL)
        e = _entry()
        e["settings"]["TiresAero.LeftFront.StartingPressure"] = "159 kPa"
        e["tires"] = {"surface_c": {"LF": {"inner": 80.0, "middle": 78.0, "outer": 76.0}},
                      "hot_pressure_kpa": {"LF": 172.4}, "pressure_stable": True,
                      "pit_snapshot": None}
        md = nb.render_markdown({"car": "c", "track": "t", "entries": [e]})
        assert "| StartingPressure | 23.1 psi |" in md
        assert "Hot pressure (psi)" in md and "| 25.0 |" in md

    def test_limits_appear_beside_settings(self):
        limits = {"settings": {"Chassis.LeftFront.Camber": {
            "min": -4.0, "max": 1.0, "unit": "deg", "linked": True}}}
        md = nb.render_markdown({"car": "c", "track": "t", "entries": [_entry()]}, limits)
        assert "| Camber | -4.0 deg | -4–1 deg; linked — iRacing checks legality |" in md


class TestDisplaySetting:
    @pytest.mark.parametrize("metric_value, imperial", [
        ("159 kPa", "23.1 psi"),
        ("-2.8 mm", "-0.110 in"),
        ("+1.5 mm", "+0.059 in"),
        ("210 N/mm", "1199 lbs/in"),
        ("3328 N", "748 lbs"),
        ("55.0 L", "14.5 gal"),
        ("90 Nm", "66 ft-lbs"),
        ("-4.0 deg", "-4.0 deg"),
        ("5 clicks", "5 clicks"),
        ("Medium friction", "Medium friction"),
    ])
    def test_matches_the_imperial_garage(self, metric_value, imperial):
        # Expected values are what the Mustang GT3 garage shows (2026-09-25).
        assert nb.display_setting(metric_value, metric=False) == imperial

    def test_snaps_to_the_garage_step(self):
        spec = {"step": 0.5, "unit": "psi"}
        assert nb._snap_to_step("23.1 psi", spec) == "23.0 psi"
        assert nb._snap_to_step("5 clicks", {"step": 1, "unit": "clicks"}) == "5 clicks"
        assert nb._snap_to_step("23.1 psi", {"step": None, "unit": "psi"}) == "23.1 psi"
        assert nb._snap_to_step("23.1 psi", {"step": 0.5, "unit": "kPa"}) == "23.1 psi"

    def test_metric_passes_through(self):
        assert nb.display_setting("159 kPa", metric=True) == "159 kPa"


# ─── End to end on a synthetic .ibt ───────────────────────────────────────────

@pytest.fixture
def synthetic_with_setup(tmp_path):
    from synthetic_ibt import build_ibt, default_session_info, default_test_corners
    info = default_session_info(track_length_km=2.0)
    info["DriverInfo"]["DriverSetupName"] = "baseline.sto"
    info["DriverInfo"]["DriverSetupIsModified"] = 0
    info["CarSetup"] = CAR_SETUP
    path = tmp_path / "testcar_testcircuit 2026-07-29 20-00-00.ibt"
    build_ibt(str(path), default_test_corners(), laps=4, track_length_m=2000.0,
              session_info=info)
    return str(path)


class TestRecordSession:
    def test_writes_notebook_notes_and_guide(self, synthetic_with_setup, tmp_path):
        root = str(tmp_path / "nb")
        md_path = nb.record_session(synthetic_with_setup, root=root)
        assert md_path and os.path.exists(md_path)
        json_path, _, notes_path = nb.notebook_paths("testcar", "testcircuit", root)
        data = json.loads(open(json_path, encoding="utf-8").read())
        assert len(data["entries"]) == 1
        assert data["entries"][0]["setup_name"] == "baseline.sto"
        assert data["entries"][0]["pace"]["best_s"] > 0
        assert os.path.exists(notes_path)
        assert os.path.exists(os.path.join(root, "ENGINEER.md"))

    def test_recording_twice_replaces_the_entry(self, synthetic_with_setup, tmp_path):
        root = str(tmp_path / "nb")
        nb.record_session(synthetic_with_setup, root=root)
        nb.record_session(synthetic_with_setup, root=root)
        json_path, _, _ = nb.notebook_paths("testcar", "testcircuit", root)
        assert len(json.load(open(json_path, encoding="utf-8"))["entries"]) == 1

    def test_driver_notes_are_never_overwritten(self, synthetic_with_setup, tmp_path):
        root = str(tmp_path / "nb")
        nb.record_session(synthetic_with_setup, root=root)
        _, _, notes_path = nb.notebook_paths("testcar", "testcircuit", root)
        with open(notes_path, "w", encoding="utf-8") as f:
            f.write("my notes")
        nb.record_session(synthetic_with_setup, root=root)
        assert open(notes_path, encoding="utf-8").read() == "my notes"

    def test_session_without_car_setup_is_skipped(self, synthetic_session, tmp_path):
        assert nb.record_session(synthetic_session["path"], root=str(tmp_path)) is None

    def test_limits_template_lists_seen_settings(self, synthetic_with_setup, tmp_path):
        root = str(tmp_path / "nb")
        nb.record_session(synthetic_with_setup, root=root)
        path, created = nb.write_limits_template("testcar", root=root)
        limits = json.load(open(path, encoding="utf-8"))
        assert created and "Chassis.LeftFront.Camber" in limits["settings"]
        assert nb.write_limits_template("testcar", root=root) == (path, False)


class TestPipelineIsolation:
    def test_notebook_failure_never_raises(self, monkeypatch):
        from tenths import process
        def boom(*a, **k):
            raise RuntimeError("disk full")
        monkeypatch.setattr(nb, "record_session", boom)
        messages = []
        assert process.record_in_notebook("x.ibt", {"car": "c", "track": "t"},
                                          log=messages.append) is None
        assert "setup notebook not updated" in messages[0]

    def test_disabled_setting_skips_capture(self, monkeypatch):
        from tenths import config, process
        monkeypatch.setitem(config.SETTINGS, "setup_notebook", False)
        called = []
        monkeypatch.setattr(nb, "record_session", lambda *a, **k: called.append(1))
        assert process.record_in_notebook("x.ibt", {}) is None
        assert not called


class TestTyresSettled:
    def _pressures(self, per_lap):
        return _laps_frame({lap: {f"{c}pressure": v for c in nb.CORNERS}
                            for lap, v in per_lap.items()})

    def test_road_atlanta_settles_at_lap_5(self):
        # Hottest-tyre psi per lap at Road Atlanta 2026-09-25.
        df = self._pressures({1: 24.1, 2: 25.0, 3: 25.8, 4: 26.3, 5: 26.6, 6: 26.9})
        assert nb.tires_settled_from(df) == 5

    def test_never_settled(self):
        df = self._pressures({1: 20.0, 2: 21.0, 3: 22.0})
        assert nb.tires_settled_from(df) is None

    def test_first_lap_has_nothing_to_compare(self):
        df = self._pressures({3: 25.0, 5: 25.0, 6: 25.0})
        assert nb.tires_settled_from(df) == 6

    def test_no_pressure_channels(self):
        assert nb.tires_settled_from(_laps_frame({1: {"Speed": 1.0}})) is None

    def test_measured_note(self):
        assert "tyres settled from lap 5" in nb._measured_note(
            {"measured_laps": [5, 6], "tires_settled_from_lap": 5})
        assert "before warm-up filtering" in nb._measured_note({})


class TestEqualGBalance:
    def test_steer_demand_is_binned_by_lateral_g(self):
        d = pd.concat([_arc(100, 35.0, 100.0, 0.5, throttle=80.0, lat_g=1.2),
                       _arc(100, 35.0, 100.0, 0.7, throttle=80.0, lat_g=1.8)],
                      ignore_index=True)
        by_g = nb.balance_profile(d, 1)["steer_demand_by_g"]["medium"]
        assert by_g["1-1.5 g"]["deg"] == pytest.approx(math.degrees(0.5), abs=0.1)
        assert by_g["1.5-2 g"]["deg"] == pytest.approx(math.degrees(0.7), abs=0.1)
        assert by_g[">2 g"] == {"deg": None, "n": 0}

    def test_braking_samples_are_excluded(self):
        d = _arc(100, 35.0, 100.0, 0.5, brake=40.0, lat_g=1.2)
        assert nb.balance_profile(d, 1)["steer_demand_by_g"]["medium"]["1-1.5 g"]["n"] == 0

    def test_near_limit_share(self):
        d = pd.concat([_arc(75, 35.0, 100.0, 0.5, throttle=80.0, lat_g=1.2),
                       _arc(25, 35.0, 100.0, 0.5, throttle=80.0, lat_g=1.8)],
                      ignore_index=True)
        assert nb.balance_profile(d, 1)["near_limit_share"] == 0.25

    def test_long_countersteer_is_located(self):
        normal = _arc(60, 20.0, 60.0, 0.5, throttle=80.0).assign(Lap=8, LapDistPct=21.0)
        slide = _arc(30, 20.0, 60.0, -0.3, throttle=0.0).assign(Lap=8, LapDistPct=21.4)
        bal = nb.balance_profile(pd.concat([normal, slide, normal], ignore_index=True), 1)
        (event,) = bal["countersteer_events"]
        assert event["lap"] == 8 and event["lap_pct"] == 21.4
        assert event["phase"] == "mid" and event["duration_s"] == 0.5


class TestPaceTrend:
    def test_slope_of_improving_driver(self):
        times = {5: 82.57, 6: 82.19, 7: 82.35, 8: 81.35, 9: 81.22, 10: 80.63}
        assert nb.pace_trend(list(times), times) == pytest.approx(-0.38, abs=0.01)

    def test_too_few_laps(self):
        assert nb.pace_trend([1, 2, 3], {1: 80.0, 2: 80.0, 3: 80.0}) is None


def _g_entry(recorded, deg, camber="-4.0 deg", n=300):
    e = _entry(camber=camber, recorded=recorded)
    e["balance"] = {"steer_demand_by_g": {"medium": {"1.5-2 g": {"deg": deg, "n": n}}}}
    return e


class TestNoiseFloor:
    def test_same_setup_pairs_set_the_noise_floor(self):
        entries = [_g_entry("2026-09-25 17:30", 35.0), _g_entry("2026-09-25 21:34", 39.0),
                   _g_entry("2026-09-25 22:17", 30.0, camber="-3.6 deg")]
        text = "\n".join(nb._repeatability_section(entries))
        assert "| 1 → 2 | 1 | 4.0 | 4.0 |" in text
        assert "2 → 3" not in text        # a setup change is not noise

    def test_thin_cells_are_ignored(self):
        entries = [_g_entry("2026-09-25 17:30", 35.0, n=50), _g_entry("2026-09-25 21:34", 39.0)]
        assert nb._repeatability_section(entries) == []


SUMMARY = {
    "source_file": "fordmustanggt3_roadatlanta full 2026-09-25 22-17-30.ibt",
    "braking_zones": [{"turn_name": "T2", "position_pct": 18.9, "entry_speed_mph": 125.1,
                       "apex_avg_mph": 71.9, "min_speed_spread_mph": 13.4}],
    "corner_variance": [{"turn_name": "T2", "position_pct": 18.9, "time_loss_s": 0.2},
                        {"turn_name": "T7", "position_pct": 51.1, "time_loss_s": 0.429}],
    "trail_braking": [{"turn_name": "T2", "diagnosis": "Good"}],
}


class TestSessionSummaryCrossReference:
    def test_corners_merge_zones_variance_and_trail(self):
        corners = nb.corners_from_summary(SUMMARY)
        t2, t7 = corners
        assert t2["turn"] == "T2" and t2["time_loss_s"] == 0.2 and t2["trail_diagnosis"] == "Good"
        assert t2["apex_avg_mps"] == pytest.approx(71.9 * 0.44704, abs=0.01)
        assert t7 == {"turn": "T7", "pct": 51.1, "time_loss_s": 0.429}

    def test_finds_the_summary_generated_from_this_file(self, tmp_path):
        info = {"car": "fordmustanggt3", "track": "roadatlanta_full",
                "date": "2026-09-25", "time": "22-17-30"}
        other = tmp_path / "fordmustanggt3" / "roadatlanta_full" / "2026-09-25" / "22-17-30"
        mine = other.parent / "22-17-30-2"
        for folder, source in ((other, "someone else.ibt"), (mine, SUMMARY["source_file"])):
            folder.mkdir(parents=True)
            (folder / "session_summary.json").write_text(json.dumps({"source_file": source}))
        path, data = nb.find_session_summary(SUMMARY["source_file"], info, str(tmp_path))
        assert path == str(mine / "session_summary.json")

    def test_missing_summary(self, tmp_path):
        info = {"car": "c", "track": "t", "date": "2026-01-01", "time": "00-00-00"}
        assert nb.find_session_summary("x.ibt", info, str(tmp_path)) == (None, None)


class TestCarNotes:
    def test_created_once_and_never_overwritten(self, synthetic_with_setup, tmp_path):
        root = str(tmp_path / "nb")
        nb.record_session(synthetic_with_setup, root=root)
        path = nb.car_notes_path("testcar", root)
        assert "How the car responds to changes" in open(path, encoding="utf-8").read()
        with open(path, "w", encoding="utf-8") as f:
            f.write("mine")
        nb.record_session(synthetic_with_setup, root=root)
        assert open(path, encoding="utf-8").read() == "mine"


class TestComparisonBase:
    def test_short_stint_is_skipped_as_a_base(self):
        full, crash, after = _entry(recorded="a"), _entry(recorded="b"), _entry(recorded="c")
        crash["pace"]["measured_laps"] = [1]
        entries = [full, crash, after]
        assert nb.comparison_base(entries, 2) == 0
        assert nb.comparison_base(entries, 0) is None


class TestABA:
    def _run(self, recorded, deg, camber="-4.0 deg", lap_s=81.0, laps=(2, 3, 4)):
        e = _g_entry(recorded, deg, camber=camber)
        e["pace"]["measured_laps"] = list(laps)
        e["pace"]["measured_mean_s"] = lap_s
        return e

    def test_detects_baseline_change_baseline(self):
        entries = [self._run("a", 35.0), self._run("b", 30.0, camber="-3.6 deg"),
                   self._run("c", 37.0)]
        assert nb.aba_tests(entries) == [(0, 1, 2)]

    def test_effect_is_measured_against_both_baselines(self):
        # Baselines 35 and 37 (drift +2), test 30: effect = 30 - 36 = -6.
        assert nb._aba_effect(35.0, 30.0, 37.0) == (-6.0, 2.0)
        assert nb._aba_effect(35.0, None, 37.0) is None

    def test_not_aba_when_the_second_baseline_differs(self):
        entries = [self._run("a", 35.0), self._run("b", 30.0, camber="-3.6 deg"),
                   self._run("c", 37.0, camber="-3.8 deg")]
        assert nb.aba_tests(entries) == []

    def test_short_stints_are_skipped(self):
        crash = self._run("b0", 20.0, camber="-3.0 deg", laps=(1,))
        entries = [self._run("a", 35.0), crash, self._run("b", 30.0, camber="-3.6 deg"),
                   self._run("c", 37.0)]
        assert nb.aba_tests(entries) == [(0, 2, 3)]

    def test_section_reports_effect_and_drift(self):
        entries = [self._run("a", 35.0, lap_s=81.0),
                   self._run("b", 30.0, camber="-3.6 deg", lap_s=80.6),
                   self._run("c", 37.0, lap_s=80.8)]
        text = "\n".join(nb._aba_section(entries))
        assert "Sessions 1 / 2 / 3: Camber -4.0 deg → -3.6 deg" in text
        assert "effect -0.300 s, drift -0.200 s" in text
        assert "-6.0 (+2.0)" in text
        assert "larger than the drift in 1 of 1 cells" in text

    def test_noise_floor_pairs_the_two_baselines(self):
        entries = [self._run("a", 35.0), self._run("b", 30.0, camber="-3.6 deg"),
                   self._run("c", 37.0)]
        assert nb.same_setup_base(entries, 2) == 0
        assert "| 1 → 3 | 1 | 2.0 | 2.0 |" in "\n".join(nb._repeatability_section(entries))


class TestSetupJitter:
    def test_ride_height_recalculation_is_not_a_change(self):
        # 2026-09-26: same lemans.sto recorded 55.0 mm where 2026-09-25 had 54.9 mm.
        a, b = _entry(), _entry()
        a["settings"]["Chassis.LeftFront.RideHeight"] = "54.9 mm"
        b["settings"]["Chassis.LeftFront.RideHeight"] = "55.0 mm"
        assert nb.setup_diff(a, b) == []

    def test_real_ride_height_change_still_counts(self):
        a, b = _entry(), _entry()
        a["settings"]["Chassis.LeftRear.RideHeight"] = "60.9 mm"
        b["settings"]["Chassis.LeftRear.RideHeight"] = "63.4 mm"
        assert [d[0] for d in nb.setup_diff(a, b)] == ["Chassis.LeftRear.RideHeight"]

    def test_other_settings_have_no_tolerance(self):
        a, b = _entry(camber="-4.0 deg"), _entry(camber="-3.9 deg")
        assert len(nb.setup_diff(a, b)) == 1


class TestPressureStableUsesTheLapBefore:
    def test_clean_laps_far_apart(self):
        # Road Atlanta 2026-09-26 LF psi: clean laps 3, 4, 7; laps 5-6 had offs.
        psi = {3: 25.6, 4: 26.0, 5: 26.3, 6: 26.4, 7: 26.5}
        df = _laps_frame({lap: {f"{c}pressure": v / 0.145038 for c in nb.CORNERS}
                          for lap, v in psi.items()})
        assert nb.tire_profile(df, [3, 4, 7], {})["pressure_stable"] is True
