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
