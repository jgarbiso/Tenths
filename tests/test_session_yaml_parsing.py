"""
Guards for session-info YAML parsing (analyzer._load_session_yaml).

Regression: iRacing writes driver-supplied free-text (names, team, initials)
into the .ibt session-info header UNQUOTED. When a value starts with a YAML
indicator character — most often a non-ASCII name mojibake'd to something like
``UserName: ? ?`` — a raw yaml.safe_load raises

    yaml.scanner.ScannerError: mapping keys are not allowed here

and the entire session fails to process. This bit a real Road America session
(2026-09-15) where car 56's driver had a CJK name. It is a long-standing iRacing
quirk, not a telemetry-format change.

_load_session_yaml sanitises the header the way pyirsdk's own _parse_yaml does
before parsing. These tests pin that a raw load still fails on the captured
header while the production helper succeeds, and cover the synthetic minimal
case so the invariant holds without depending on the 18 KB fixture.
"""

import os

import pytest
import yaml

from tenths.analyzer import _load_session_yaml

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "session_info_nonascii_name.yaml")


def _fixture_bytes():
    # Stored in the same latin-1/cp1252 space the header uses.
    with open(FIXTURE, "rb") as f:
        return f.read()


class TestToxicNameRegression:
    def test_raw_safe_load_still_fails_on_the_captured_header(self):
        """If this ever stops raising, the fixture no longer reproduces the bug
        and the rest of these tests would be proving nothing."""
        text = _fixture_bytes().decode("cp1252")
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(text)

    def test_helper_parses_the_captured_header(self):
        info = _load_session_yaml(_fixture_bytes())
        assert info is not None
        wi = info.get("WeekendInfo", {})
        assert wi.get("TrackID") == 596
        assert wi.get("TrackDisplayName") == "Road America"

    def test_toxic_driver_name_survives_as_a_string(self):
        info = _load_session_yaml(_fixture_bytes())
        drivers = info.get("DriverInfo", {}).get("Drivers", [])
        car56 = next((d for d in drivers if d.get("CarIdx") == 56), None)
        assert car56 is not None, "the toxic driver must still be present"
        # It parses to a string rather than blowing up the document.
        assert isinstance(car56.get("UserName"), str)


class TestSyntheticIndicatorValues:
    """Minimal cases, independent of the large fixture, for each free-text field
    that iRacing leaves unquoted and can start with a YAML indicator."""

    def _wrap(self, driver_lines):
        doc = (
            "WeekendInfo:\n"
            " TrackID: 1\n"
            " TrackDisplayName: Test\n"
            "DriverInfo:\n"
            " DriverCarIdx: 0\n"
            " Drivers:\n"
            " - CarIdx: 0\n"
            + driver_lines
        )
        return doc.encode("cp1252")

    def test_username_starting_with_question_mark(self):
        info = _load_session_yaml(self._wrap("   UserName: ? ?\n"))
        assert info["DriverInfo"]["Drivers"][0]["UserName"] == "? ?"

    def test_teamname_with_colon(self):
        info = _load_session_yaml(self._wrap("   TeamName: Racing: Team\n"))
        assert info["DriverInfo"]["Drivers"][0]["TeamName"] == "Racing: Team"

    def test_initials_starting_with_comma(self):
        info = _load_session_yaml(self._wrap("   Initials: ,X\n"))
        assert info["DriverInfo"]["Drivers"][0]["Initials"] == ",X"

    def test_embedded_quote_is_escaped_not_fatal(self):
        info = _load_session_yaml(self._wrap('   UserName: A "B" C\n'))
        assert info["DriverInfo"]["Drivers"][0]["UserName"] == 'A "B" C'

    def test_ordinary_ascii_name_is_unchanged(self):
        info = _load_session_yaml(self._wrap("   UserName: Justin Garbiso\n"))
        assert info["DriverInfo"]["Drivers"][0]["UserName"] == "Justin Garbiso"


def test_empty_header_returns_none_or_empty():
    """A blank/zero header must not raise."""
    result = _load_session_yaml(b"\x00\x00\x00")
    assert result is None or result == {} or isinstance(result, dict)
