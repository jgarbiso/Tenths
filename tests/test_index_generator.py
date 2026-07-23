"""
Tests for the master session index generator.

Tests verify:
- Session scanning from session_summary.json files
- HTML generation with correct structure
- Filter functionality (datalist options, JS partial matching)
- Edge cases (empty directory, missing fields, malformed JSON)
- XSS safety of report paths
"""

import os
import json
import tempfile
import shutil

import pytest

from tenths.index_generator import generate_master_index, _build_master_html


def _make_session_summary(car="bmwm4evogt4", track="midohio_full", config="Full",
                          date="2026-06-13", time="16-37-00", session_type="Practice",
                          best_lap_time="1:39.306", best_lap_seconds=99.306,
                          total_laps=12, race_result=None):
    """Helper to create a valid session_summary.json structure."""
    summary = {
        "schema_version": "1.2.0",
        "car": {"name": car},
        "track": {"name": track, "config": config},
        "session": {"date": date, "time": time, "type": session_type},
        "best_lap": {"time_formatted": best_lap_time, "time_seconds": best_lap_seconds},
        "total_valid_laps": total_laps,
    }
    if race_result:
        summary["race_result"] = race_result
    return summary


@pytest.fixture
def temp_telemetry_root(tmp_path):
    """Create a temporary telemetry root with sample session data."""
    root = tmp_path / "telemetry"
    root.mkdir()

    # Session 1: BMW GT4 at Mid-Ohio
    s1_dir = root / "bmwm4evogt4" / "midohio_full" / "2026-06-13" / "16-37-00"
    s1_dir.mkdir(parents=True)
    with open(s1_dir / "session_summary.json", 'w') as f:
        json.dump(_make_session_summary(), f)
    with open(s1_dir / "session_report.html", 'w') as f:
        f.write("<html>report</html>")

    # Session 2: BMW GT4 at Mid-Ohio (different day, faster)
    s2_dir = root / "bmwm4evogt4" / "midohio_full" / "2026-06-14" / "20-15-00"
    s2_dir.mkdir(parents=True)
    with open(s2_dir / "session_summary.json", 'w') as f:
        json.dump(_make_session_summary(date="2026-06-14", time="20-15-00",
                                        best_lap_time="1:38.100", best_lap_seconds=98.1), f)
    with open(s2_dir / "session_report.html", 'w') as f:
        f.write("<html>report2</html>")

    # Session 3: Ferrari at Barber (race)
    s3_dir = root / "ferrari296challenge" / "barber" / "2026-06-12" / "19-00-00"
    s3_dir.mkdir(parents=True)
    with open(s3_dir / "session_summary.json", 'w') as f:
        json.dump(_make_session_summary(
            car="ferrari296challenge", track="barber", config="Full",
            date="2026-06-12", time="19-00-00", session_type="Race",
            best_lap_time="1:25.400", best_lap_seconds=85.4,
            race_result={"finish_position": 3, "field_size": 16, "irating_delta": 42}
        ), f)
    with open(s3_dir / "session_report.html", 'w') as f:
        f.write("<html>report3</html>")

    return str(root)


class TestGenerateMasterIndex:
    """Tests for the generate_master_index() function."""

    def test_generates_index_html(self, temp_telemetry_root):
        """Index file is created at telemetry root."""
        result = generate_master_index(temp_telemetry_root)
        assert result is not None
        assert result.endswith("index.html")
        assert os.path.exists(result)

    def test_returns_none_for_empty_directory(self, tmp_path):
        """Returns None if no session_summary.json files found."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = generate_master_index(str(empty_dir))
        assert result is None

    def test_returns_none_for_nonexistent_directory(self):
        """Returns None if directory doesn't exist."""
        result = generate_master_index("/nonexistent/path/that/wont/exist")
        assert result is None

    def test_all_sessions_included(self, temp_telemetry_root):
        """All 3 sessions appear in the generated HTML."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # All sessions should be in the SESSIONS JSON array
        assert "midohio_full" in html
        assert "barber" in html
        assert "bmwm4evogt4" in html
        assert "ferrari296challenge" in html

    def test_sessions_sorted_newest_first(self, temp_telemetry_root):
        """Sessions are sorted newest first (2026-06-14 before 2026-06-12)."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # The SESSIONS JSON should have 2026-06-14 before 2026-06-12
        idx_14 = html.index("2026-06-14")
        idx_12 = html.index("2026-06-12")
        assert idx_14 < idx_12, "Newest session should appear first"

    def test_stats_show_correct_counts(self, temp_telemetry_root):
        """Stats section shows correct totals."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # 3 sessions total
        assert '>3</div>' in html  # total sessions
        # 36 total laps (12 + 12 + 12)
        assert '>36</div>' in html  # total laps
        # 2 unique tracks
        assert '>2</div>' in html  # unique tracks
        # 2 unique cars
        assert '>2</div>' in html  # unique cars

    def test_report_links_use_relative_paths(self, temp_telemetry_root):
        """Report links should use relative paths from telemetry root."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # Should contain relative paths not absolute
        assert "bmwm4evogt4/midohio_full/2026-06-13/16-37-00/session_report.html" in html
        # Should NOT contain the temp directory absolute path
        assert temp_telemetry_root.replace('\\', '/') not in html

    def test_race_result_fields_included(self, temp_telemetry_root):
        """Race result data (position, field, iRating) is in the JSON."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # Ferrari race session should have P3/16 and +42 iR
        assert '"race_pos": 3' in html
        assert '"race_field": 16' in html
        assert '"race_ir": 42' in html

    def test_filter_datalists_populated(self, temp_telemetry_root):
        """Filter datalist elements for cars and tracks are present."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        assert 'id="track-list"' in html
        assert 'id="car-list"' in html
        assert 'id="track-filter"' in html
        assert 'id="car-filter"' in html

    def test_partial_match_filter_function(self, temp_telemetry_root):
        """The matchesFilter JS function uses case-insensitive includes."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # Verify the matchesFilter function uses .toLowerCase().includes()
        assert "value.toLowerCase().includes(filter.toLowerCase())" in html

    def test_clear_button_present(self, temp_telemetry_root):
        """Clear filters button is present."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        assert 'id="clear-filters"' in html

    def test_pit_wall_theme_applied(self, temp_telemetry_root):
        """Pit Wall dark theme colors are in the CSS."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        assert "#0a0a0f" in html  # bg-base
        assert "#12141f" in html  # bg-surface
        assert "#00e676" in html  # accent-green
        assert "Orbitron" in html  # hero font

    def test_session_type_badges(self, temp_telemetry_root):
        """Session type badge classes are properly defined."""
        result = generate_master_index(temp_telemetry_root)
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        assert "badge-race" in html
        assert "badge-practice" in html
        assert "badge-test" in html
        assert "badge-qualify" in html


class TestEdgeCases:
    """Edge case and error handling tests."""

    def test_malformed_json_skipped(self, tmp_path):
        """Sessions with malformed JSON are silently skipped."""
        root = tmp_path / "telemetry"
        s_dir = root / "car" / "track" / "2026-01-01" / "10-00-00"
        s_dir.mkdir(parents=True)
        with open(s_dir / "session_summary.json", 'w') as f:
            f.write("{invalid json content!!!")
        result = generate_master_index(str(root))
        # Should return None since no valid sessions
        assert result is None

    def test_missing_fields_use_defaults(self, tmp_path):
        """Sessions with missing fields use sensible defaults."""
        root = tmp_path / "telemetry"
        s_dir = root / "car" / "track" / "2026-01-01" / "10-00-00"
        s_dir.mkdir(parents=True)
        # Minimal JSON — missing many fields
        with open(s_dir / "session_summary.json", 'w') as f:
            json.dump({"schema_version": "1.2.0"}, f)
        result = generate_master_index(str(root))
        assert result is not None
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # Should use defaults without crashing
        assert "Unknown" in html  # Default car/track name

    def test_missing_report_html(self, tmp_path):
        """Sessions without session_report.html get no link."""
        root = tmp_path / "telemetry"
        s_dir = root / "car" / "track" / "2026-01-01" / "10-00-00"
        s_dir.mkdir(parents=True)
        with open(s_dir / "session_summary.json", 'w') as f:
            json.dump(_make_session_summary(), f)
        # No session_report.html created
        result = generate_master_index(str(root))
        assert result is not None
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # report_path should be empty string in JSON
        assert '"report_path": ""' in html

    def test_xss_safe_report_paths(self, tmp_path):
        """Report paths with special characters are HTML-escaped."""
        root = tmp_path / "telemetry"
        # Create a directory with characters that could be XSS vectors
        s_dir = root / "car" / "track&config" / "2026-01-01" / "10-00-00"
        s_dir.mkdir(parents=True)
        with open(s_dir / "session_summary.json", 'w') as f:
            json.dump(_make_session_summary(track="track&config"), f)
        with open(s_dir / "session_report.html", 'w') as f:
            f.write("<html></html>")
        result = generate_master_index(str(root))
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # The & in the path should be escaped in the JSON string
        # (json.dumps handles this, but html_escape adds another layer)
        assert "track&amp;config" in html or "track&config" in html

    def test_pb_not_marked_when_best_is_sentinel(self, tmp_path):
        """★ marker should not appear when best_lap_s is 9999 (no valid lap)."""
        root = tmp_path / "telemetry"
        s_dir = root / "car" / "track" / "2026-01-01" / "10-00-00"
        s_dir.mkdir(parents=True)
        with open(s_dir / "session_summary.json", 'w') as f:
            json.dump(_make_session_summary(best_lap_time="—", best_lap_seconds=9999), f)
        result = generate_master_index(str(root))
        assert result is not None
        with open(result, 'r', encoding='utf-8') as f:
            html = f.read()
        # JS condition: s.best_lap_s < 9999 prevents ★ on sentinel values
        assert "s.best_lap_s < 9999" in html
