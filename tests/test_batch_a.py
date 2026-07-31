"""
RR-002 (JSON normalisation) and RR-005 (startup scan).

RR-002: `default=str` turned NumPy values into strings, so a session summary
could contain `"is_new_pb": "False"` — truthy in JavaScript, which displayed a
"New PB" badge on a session that was not a PB.

RR-005: filesystem events only fire while the watcher runs, so a session
recorded before Tenths started was ignored until something modified it again.
"""

import json
import os
import time

import numpy as np
import pytest

from tenths.jsonio import dump_json, dumps_json, to_jsonable
from tenths.service.watcher import MIN_FILE_SIZE, TelemetryWatcher


class TestJsonNormalisation:

    def test_numpy_false_becomes_json_false(self):
        """The exact defect: numpy.bool_(False) must not become "False"."""
        assert to_jsonable(np.bool_(False)) is False
        assert dumps_json({"is_new_pb": np.bool_(False)}) == '{"is_new_pb": false}'

    def test_numpy_true_becomes_json_true(self):
        assert to_jsonable(np.bool_(True)) is True
        assert dumps_json({"x": np.bool_(True)}) == '{"x": true}'

    def test_string_false_would_be_truthy_in_js(self):
        """Documents why this matters, guarding against a regression."""
        assert bool("False") is True

    def test_numpy_numeric_types(self):
        assert to_jsonable(np.int64(7)) == 7
        assert isinstance(to_jsonable(np.int64(7)), int)
        assert to_jsonable(np.float64(1.5)) == 1.5
        assert isinstance(to_jsonable(np.float64(1.5)), float)

    def test_numpy_arrays_become_lists(self):
        assert to_jsonable(np.array([1, 2, 3])) == [1, 2, 3]
        assert to_jsonable(np.array([[1.0, 2.0]])) == [[1.0, 2.0]]

    def test_nested_structures(self):
        payload = {
            "progression": {"alltime_best": {"is_new_pb": np.bool_(False)}},
            "laps": [{"time": np.float64(91.5), "abs": np.int32(12)}],
        }
        result = to_jsonable(payload)
        assert result["progression"]["alltime_best"]["is_new_pb"] is False
        assert result["laps"][0]["time"] == 91.5
        assert result["laps"][0]["abs"] == 12

    def test_non_finite_floats_become_null(self):
        """NaN and Infinity are not valid JSON."""
        assert to_jsonable(float("nan")) is None
        assert to_jsonable(float("inf")) is None
        assert to_jsonable(np.float64("nan")) is None

    def test_tuples_and_sets_become_lists(self):
        assert to_jsonable((1, 2)) == [1, 2]
        assert sorted(to_jsonable({1, 2})) == [1, 2]

    def test_bool_not_treated_as_int(self):
        assert to_jsonable(True) is True
        assert to_jsonable(False) is False

    def test_unsupported_type_raises_rather_than_stringifies(self):
        class Custom:
            pass

        with pytest.raises(TypeError, match="not JSON-serialisable"):
            to_jsonable(Custom())

    def test_dump_json_writes_valid_json(self, tmp_path):
        target = tmp_path / "out.json"
        with open(target, "w", encoding="utf-8") as f:
            dump_json({"pb": np.bool_(False), "t": np.float64(90.1)}, f, indent=2)
        with open(target, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["pb"] is False
        assert loaded["t"] == 90.1


class TestSummaryAndReportSerialisation:
    """The production writers must emit real booleans."""

    def _write_history(self, track_dir, date, best_time):
        session = track_dir / date
        session.mkdir(parents=True, exist_ok=True)
        with open(session / "session_summary.json", "w", encoding="utf-8") as f:
            json.dump({
                "schema_version": "1.0.0",
                "session": {"date": date},
                "best_lap": {"time_seconds": best_time},
                "abs": {"cleanest_hits": 10, "per_lap_totals": [10]},
                "total_recoverable_time_s": 1.0,
            }, f)

    def test_computed_pb_flag_is_a_real_boolean(self, tmp_path):
        """The real path: progression is computed from NumPy-derived lap times.

        write_session_summary recomputes progression, so the flag under test is
        the one production actually generates, not a hand-set value.
        """
        from tenths.summary import write_session_summary
        # A faster previous session, so this one is NOT a PB
        self._write_history(tmp_path, "2026-07-28", 90.0)
        current = tmp_path / "2026-07-29"
        current.mkdir()

        summary = {
            "schema_version": "1.0.0",
            "session": {"date": "2026-07-29"},
            "best_lap": {"time_seconds": np.float64(91.0)},
            "abs": {"cleanest_hits": np.int64(10), "per_lap_totals": [np.int64(10)]},
            "total_recoverable_time_s": np.float64(1.0),
        }
        path = write_session_summary(summary, str(current))
        raw = open(path, encoding="utf-8").read()
        loaded = json.loads(raw)

        assert loaded["progression"] is not None, "history should have been found"
        flag = loaded["progression"]["alltime_best"]["is_new_pb"]
        assert flag is False, f"expected a real boolean False, got {flag!r}"
        assert '"is_new_pb": "False"' not in raw

    def test_no_stringified_booleans_anywhere(self, tmp_path):
        from tenths.summary import write_session_summary
        summary = {
            "schema_version": "1.0.0",
            "session": {"date": "2026-07-29"},
            "best_lap": {"time_seconds": 91.0},
            "abs": {"cleanest_hits": 1, "per_lap_totals": [1]},
            "total_recoverable_time_s": 1.0,
            "flags": {"a": np.bool_(True), "b": np.bool_(False)},
        }
        path = write_session_summary(summary, str(tmp_path))
        raw = open(path, encoding="utf-8").read()
        assert '"True"' not in raw and '"False"' not in raw

    def test_report_embeds_boolean_pb(self, synthetic_data, synthetic_file_info):
        from tenths.report import generate_report
        progression = {
            "previous_session": {"date": "2026-07-28", "best_lap_time_s": 90.0},
            "delta_vs_previous": {"lap_time_s": 1.0, "cleanest_abs": 0,
                                 "total_recoverable_s": 0.0},
            "alltime_best": {"lap_time_s": 90.0, "date": "2026-07-28",
                            "is_new_pb": np.bool_(False)},
            "session_count": 2,
            "trend": {"lap_times": [90.0, 91.0], "dates": ["a", "b"], "abs_avgs": [1, 2]},
        }
        html = generate_report(synthetic_data, synthetic_file_info, None,
                              progression=progression)
        assert '"is_new_pb": false' in html
        assert '"is_new_pb": "False"' not in html

    def test_real_session_summary_is_clean(self, synthetic_data, synthetic_file_info, tmp_path):
        """End to end with genuine analyser output, which is full of NumPy types."""
        from tenths.summary import generate_session_summary, write_session_summary
        summary = generate_session_summary(synthetic_data, synthetic_file_info, None)
        path = write_session_summary(summary, str(tmp_path))
        raw = open(path, encoding="utf-8").read()
        assert '"True"' not in raw and '"False"' not in raw
        json.loads(raw)   # must be valid JSON


class TestStartupScan:
    """RR-005: sessions recorded while Tenths was stopped must be processed."""

    def _big_ibt(self, directory, name="testcar_testtrack 2026-07-29 20-00-00.ibt"):
        path = os.path.join(str(directory), name)
        with open(path, "wb") as f:
            f.write(b"x" * (MIN_FILE_SIZE + 1000))
        return path

    def test_existing_file_is_queued(self, tmp_path):
        path = self._big_ibt(tmp_path)
        w = TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)
        from tenths.service.watcher import IBTHandler
        w._handler = IBTHandler(lambda p: None)
        assert w._scan_existing() == 1
        assert path in w._handler._pending

    def test_undersized_file_is_ignored(self, tmp_path):
        small = os.path.join(str(tmp_path), "tiny_track 2026-07-29 20-00-00.ibt")
        with open(small, "wb") as f:
            f.write(b"x" * 100)
        w = TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)
        from tenths.service.watcher import IBTHandler
        w._handler = IBTHandler(lambda p: None)
        assert w._scan_existing() == 0

    def test_non_ibt_files_ignored(self, tmp_path):
        for name in ("notes.md", "index.html", "result.csv"):
            with open(os.path.join(str(tmp_path), name), "wb") as f:
                f.write(b"x" * (MIN_FILE_SIZE + 10))
        w = TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)
        from tenths.service.watcher import IBTHandler
        w._handler = IBTHandler(lambda p: None)
        assert w._scan_existing() == 0

    def test_archive_and_session_dirs_not_scanned(self, tmp_path):
        """Only the root is scanned; archived and processed files are skipped."""
        archive = tmp_path / "_archive"
        archive.mkdir()
        self._big_ibt(archive)
        session = tmp_path / "bmwm2csr"
        session.mkdir()
        self._big_ibt(session)
        w = TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)
        from tenths.service.watcher import IBTHandler
        w._handler = IBTHandler(lambda p: None)
        assert w._scan_existing() == 0

    def test_already_known_file_not_requeued(self, tmp_path):
        path = self._big_ibt(tmp_path)
        w = TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)
        from tenths.service.watcher import IBTHandler
        w._handler = IBTHandler(lambda p: None)
        w._claim(path)             # pretend it is already being processed
        assert w._scan_existing() == 0

    def test_queued_file_reaches_the_ready_callback(self, tmp_path):
        """A stable pre-existing file must actually be dispatched."""
        path = self._big_ibt(tmp_path)
        # Backdate so the stability wait is already satisfied
        old = time.time() - 3600
        os.utime(path, (old, old))

        ready = []
        w = TelemetryWatcher(telemetry_root=str(tmp_path), auto_open=False)
        from tenths.service.watcher import IBTHandler
        w._handler = IBTHandler(ready.append)
        w._scan_existing()
        w._handler.check_pending()
        assert ready == [path]

    def test_missing_root_scan_is_safe(self, tmp_path):
        w = TelemetryWatcher(telemetry_root=str(tmp_path / "nope"), auto_open=False)
        from tenths.service.watcher import IBTHandler
        w._handler = IBTHandler(lambda p: None)
        assert w._scan_existing() == 0   # logs, does not raise

    def test_track_existing_uses_file_mtime(self, tmp_path):
        """A recently written file must still wait out the stability window."""
        path = self._big_ibt(tmp_path)
        from tenths.service.watcher import IBTHandler
        handler = IBTHandler(lambda p: None)
        handler.track_existing(path)
        # Freshly created, so it is not yet considered stable
        ready = []
        handler._on_file_ready = ready.append
        handler.check_pending()
        assert ready == []


class TestCarClassAndProfile:
    """RR-008: a GT3 must not be labelled Touring nor judged by GT4 rules."""

    def test_gt3_metadata_does_not_return_touring(self):
        from tenths.analyzer import detect_car_class, PROFILE_GENERIC
        assert detect_car_class("ferrari296gt3", "GT3 Class") == PROFILE_GENERIC

    def test_gt4_metadata_selects_gt4_physics(self):
        from tenths.analyzer import detect_car_class, PROFILE_GT4
        assert detect_car_class("someunknowncar", "GT4 Class") == PROFILE_GT4

    def test_gt4_slug_metadata_still_detected(self):
        """iRacing sometimes reports a slug like 'bmwm4evogt4' as the class."""
        from tenths.analyzer import detect_car_class, PROFILE_GT4
        assert detect_car_class("bmwm4evogt4", "bmwm4evogt4") == PROFILE_GT4

    def test_filename_fallback_when_metadata_absent(self):
        from tenths.analyzer import detect_car_class, PROFILE_GT4, PROFILE_GENERIC
        assert detect_car_class("bmwm4evogt4", None) == PROFILE_GT4
        assert detect_car_class("ferrari296gt3", None) == PROFILE_GENERIC

    def test_touring_is_no_longer_a_profile(self):
        """The misleading catch-all name must be gone."""
        from tenths.analyzer import detect_car_class
        for vehicle, class_short in (("ferrari296gt3", "GT3 Class"),
                                    ("ministock", "Mini Stock"),
                                    ("unknown", None)):
            assert detect_car_class(vehicle, class_short) != "Touring"

    def test_display_uses_readable_class_name(self):
        from tenths.analyzer import display_car_class
        assert display_car_class({"car_class_short": "GT3 Class"}) == "GT3 Class"

    def test_display_rejects_slug_class_names(self):
        """A slug must never reach the driver's report."""
        from tenths.analyzer import display_car_class
        assert display_car_class({"car_class_short": "bmwm4evogt4"}, "GT4") == "GT4"

    def test_display_falls_back_to_profile_without_metadata(self):
        from tenths.analyzer import display_car_class
        assert display_car_class({}, "Generic") == "Generic"

    def test_analyzer_exposes_both_values(self, synthetic_data):
        """Physics profile and displayed class are separate fields."""
        assert synthetic_data["physics_profile"] in ("GT4", "Generic")
        # The synthetic session declares GT3, so it must display as GT3
        assert synthetic_data["car_class_display"] == "GT3 Class"
        assert synthetic_data["physics_profile"] == "Generic"

    def test_summary_reports_iracing_class(self, synthetic_data, synthetic_file_info):
        from tenths.summary import generate_session_summary
        summary = generate_session_summary(synthetic_data, synthetic_file_info, None)
        assert summary["car"]["class"] == "GT3 Class"
        assert summary["car"]["physics_profile"] == "Generic"


class TestSpeedRelativeThresholds:
    """RR-021: trigger levels must scale with corner speed."""

    def test_limits_scale_with_apex_speed(self, tmp_path):
        from synthetic_ibt import build_ibt, Corner
        from tenths.analyzer import analyze

        path = tmp_path / "testcar_testtrack 2026-07-29 20-00-00.ibt"
        # A slow hairpin and a fast sweeper, both perfectly consistent
        build_ibt(str(path), [Corner(pct=0.25, apex_speeds=18.0),
                              Corner(pct=0.75, apex_speeds=40.0)],
                  laps=6, track_length_m=3000.0)
        data = analyze(str(path))
        slow, fast = data["apex_consistency"]

        assert slow["spread_limit_mph"] < fast["spread_limit_mph"], (
            "a fast corner must tolerate a larger absolute spread")
        assert slow["over_braking_limit_mph"] < fast["over_braking_limit_mph"]

    def test_floor_applies_to_very_slow_corners(self, tmp_path):
        from synthetic_ibt import build_ibt, Corner
        from tenths.analyzer import analyze, SPREAD_LIMIT_FLOOR_MPH

        path = tmp_path / "testcar_testtrack 2026-07-29 21-00-00.ibt"
        build_ibt(str(path), [Corner(pct=0.3, apex_speeds=8.0),
                              Corner(pct=0.8, apex_speeds=30.0)],
                  laps=6, track_length_m=3000.0)
        data = analyze(str(path))
        assert data["apex_consistency"][0]["spread_limit_mph"] >= SPREAD_LIMIT_FLOOR_MPH

    def test_consistent_fast_corner_does_not_trigger(self, tmp_path):
        """The Qualcomm symptom: fast corners firing on normal variation."""
        from synthetic_ibt import build_ibt, Corner
        from tenths.analyzer import analyze

        path = tmp_path / "testcar_testtrack 2026-07-29 22-00-00.ibt"
        # ~90mph apex with a few mph of ordinary variation
        build_ibt(str(path), [Corner(pct=0.3, apex_speeds=[40.0, 41.0, 40.5, 39.5, 40.0, 41.0]),
                              Corner(pct=0.8, apex_speeds=25.0)],
                  laps=6, track_length_m=4000.0)
        data = analyze(str(path))
        zone = data["apex_consistency"][0]
        assert zone["min_speed_spread_mph"] <= zone["spread_limit_mph"], (
            "ordinary variation on a fast corner triggered a coaching sentence")

    def test_genuinely_inconsistent_corner_still_triggers(self, tmp_path):
        from synthetic_ibt import build_ibt, Corner
        from tenths.analyzer import analyze

        path = tmp_path / "testcar_testtrack 2026-07-29 23-00-00.ibt"
        build_ibt(str(path), [Corner(pct=0.3, apex_speeds=[18.0, 30.0, 20.0, 28.0, 19.0, 29.0]),
                              Corner(pct=0.8, apex_speeds=25.0)],
                  laps=6, track_length_m=4000.0)
        data = analyze(str(path))
        zone = data["apex_consistency"][0]
        assert zone["min_speed_spread_mph"] > zone["spread_limit_mph"]

    def test_limits_are_exposed_to_the_report(self, synthetic_data, synthetic_file_info):
        from tenths.report import generate_report
        html = generate_report(synthetic_data, synthetic_file_info, None)
        assert "spread_limit_mph" in html
        assert "over_braking_limit_mph" in html
        assert "apex_std_limit_mph" in html


class TestResultParsingRobustness:
    """RR-010: one bad field must not cost the whole race result."""

    def _csv(self, tmp_path, rows):
        header = ("Series,Season Year,Season Quarter,Race Week,Track,"
                  "Strength of Field,Start Time\n")
        meta = "Test Series,2026,3,1,Test Track,1500,2026-07-29 20:00\n"
        cols = ("Fin Pos,Name,Car,Car Class,Start Pos,Laps Comp,Inc,Interval,"
                "Average Lap Time,Fastest Lap Time,Fast Lap#,Cust ID,"
                "Old iRating,New iRating,Old License Level,Old License Sub-Level,"
                "New License Level,New License Sub-Level,Out\n")
        path = tmp_path / "eventresult_1_0.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + meta + "\n" + cols + "".join(rows))
        return str(path)

    def _row(self, fin="1", cust="1000", ir_old="1500", ir_new="1520", inc="0"):
        return (f"{fin},Driver {cust},Car,GT3,{fin},10,{inc},-,1:30.000,1:29.500,3,"
                f"{cust},{ir_old},{ir_new},12,300,12,310,Running\n")

    def test_malformed_numeric_field_does_not_lose_the_file(self, tmp_path):
        from tenths.results import parse_result
        path = self._csv(tmp_path, [
            self._row(fin="1", cust="1000"),
            self._row(fin="NA", cust="2000", ir_old="", inc="x"),   # junk values
            self._row(fin="3", cust="1434150"),
        ])
        data = parse_result(path, my_cust_id=1434150)
        assert data is not None, "a single malformed row discarded the whole file"
        assert len(data["results"]) == 3
        assert data["my_result"] is not None
        assert data["my_result"]["finish_pos"] == 3

    def test_blank_irating_becomes_zero(self, tmp_path):
        from tenths.results import parse_result
        path = self._csv(tmp_path, [self._row(cust="1434150", ir_old="", ir_new="")])
        data = parse_result(path, my_cust_id=1434150)
        assert data["my_result"]["old_irating"] == 0
        assert data["my_result"]["new_irating"] == 0

    def test_string_customer_id_matches_int(self, tmp_path):
        from tenths.results import parse_result
        path = self._csv(tmp_path, [self._row(cust="1434150")])
        assert parse_result(path, my_cust_id="1434150")["my_result"] is not None
        assert parse_result(path, my_cust_id=1434150)["my_result"] is not None

    def test_same_customer_helper(self):
        from tenths.results import _same_customer
        assert _same_customer(1434150, "1434150") is True
        assert _same_customer("1434150", 1434150) is True
        assert _same_customer(1434150, 1434150) is True
        assert _same_customer(1434150, 999) is False
        assert _same_customer(1434150, None) is False
        assert _same_customer(None, 1434150) is False

    def test_json_numeric_junk_tolerated(self, tmp_path):
        import json as _json
        from tenths.results import parse_result
        payload = {"session_results": [{"simsession_name": "RACE", "results": [
            {"finish_position": 0, "display_name": "A", "cust_id": 1434150,
             "laps_complete": "bad", "incidents": None, "oldi_rating": "",
             "newi_rating": 1520, "average_lap": "x", "best_lap_time": 895000},
            "not a dict",
        ]}]}
        path = tmp_path / "eventresult-1.json"
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(payload, f)
        data = parse_result(str(path), my_cust_id="1434150")
        assert data is not None
        assert len(data["results"]) == 1, "unusable row should be skipped, valid kept"
        assert data["my_result"]["laps_completed"] == 0
        assert data["my_result"]["new_irating"] == 1520


class TestStartupCommandAndTrackOverride:
    """RR-020 and RR-015."""

    def test_source_startup_command_launches_the_tray(self, fake_registry):
        from tenths.service.tray import TenthsTray
        cmd = TenthsTray()._startup_command()
        assert cmd.startswith('"')
        assert "tenths.cli" in cmd and "tray" in cmd

    def test_frozen_startup_command_is_just_the_exe(self, fake_registry, monkeypatch):
        import sys as _sys
        from tenths.service.tray import TenthsTray
        monkeypatch.setattr(_sys, "frozen", True, raising=False)
        monkeypatch.setattr(_sys, "executable", r"C:\Program Files\Tenths\Tenths.exe")
        cmd = TenthsTray()._startup_command()
        assert cmd == r'"C:\Program Files\Tenths\Tenths.exe"'
        assert "-m" not in cmd

    def test_tracks_override_takes_precedence(self):
        import tenths.track_map as tm
        assert tm.TRACK_MAPS_DIRS[0] == os.environ.get('TENTHS_TRACKS_DIR', ''), \
            "the override must be searched first, not last"

    def test_override_dir_is_searched_even_if_bundled_exists(self, tmp_path, monkeypatch):
        """The bundled folder must not shadow an override that has the map."""
        import tenths.track_map as tm
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        (bundled / "unrelated.md").write_text("## Turn Map\n", encoding="utf-8")
        override = tmp_path / "override"
        override.mkdir()
        (override / "mytrack.md").write_text(
            "## Turn Map\n\n| Pct | Turn | Name |\n|---|---|---|\n| ~10% | **T1** | Alpha |\n",
            encoding="utf-8")

        monkeypatch.setattr(tm, "TRACK_MAPS_DIRS", [str(override), str(bundled)])
        zones = tm._load_from_md_file("mytrack")
        assert zones, "override directory was not searched"
        assert zones[0]["turn"] == "T1"

    def test_falls_through_to_later_dir_when_first_lacks_the_map(self, tmp_path, monkeypatch):
        import tenths.track_map as tm
        first = tmp_path / "first"
        first.mkdir()
        second = tmp_path / "second"
        second.mkdir()
        (second / "mytrack.md").write_text(
            "## Turn Map\n\n| Pct | Turn | Name |\n|---|---|---|\n| ~20% | **T2** | Beta |\n",
            encoding="utf-8")

        monkeypatch.setattr(tm, "TRACK_MAPS_DIRS", [str(first), str(second)])
        zones = tm._load_from_md_file("mytrack")
        assert zones, "search stopped at the first existing directory"
        assert zones[0]["turn"] == "T2"


class TestPackagingMetadata:
    """RR-011 (metadata only; signing needs a certificate)."""

    def test_version_resource_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "installer", "version_info.txt")
        assert os.path.isfile(path)
        content = open(path, encoding="utf-8").read()
        for field in ("ProductName", "FileDescription", "FileVersion",
                      "ProductVersion", "CompanyName"):
            assert field in content

    def test_spec_references_the_version_resource(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "installer", "tenths.spec")
        assert "version_info.txt" in open(path, encoding="utf-8").read()

    def test_version_matches_config(self):
        from tenths.config import VERSION
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "installer", "version_info.txt")
        content = open(path, encoding="utf-8").read()
        assert VERSION in content, f"version resource does not mention {VERSION}"
