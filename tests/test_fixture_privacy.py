"""
Guards the committed telemetry fixtures against leaking personal data.

The fixtures in tests/data are real iRacing sessions, trimmed and scrubbed by
tools/make_test_fixture.py. An .ibt normally embeds the entire driver list for
the session: real names, customer IDs, abbreviations, initials and team names.
Even open practice sessions list everyone on the server.

If someone regenerates a fixture without scrubbing, or adds a new one straight
from their archive, these tests fail before it can be published.
"""

import glob
import os
import re
import struct

import pytest
import yaml

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

ALLOWED_NAMES = {"Test Driver", "Driver, Test", "TD", "Test Team"}

# Sections that may carry identities or setup detail and are not needed by the
# analyser, so must have been dropped.
FORBIDDEN_SECTIONS = {"QualifyResultsInfo", "CameraInfo", "RadioInfo",
                      "SplitTimeInfo", "CarSetup"}


def fixture_paths():
    return sorted(glob.glob(os.path.join(FIXTURE_DIR, "*.ibt")))


def read_info(path):
    with open(path, "rb") as f:
        header = f.read(112)
        _, info_len, info_offset = struct.unpack_from("iii", header, 12)
        f.seek(info_offset)
        raw = f.read(info_len).decode("latin-1").rstrip("\x00")
    return yaml.safe_load(raw)


def test_fixtures_exist():
    """The committed fixtures must be present, or integration tests silently degrade."""
    paths = fixture_paths()
    assert paths, (
        f"No .ibt fixtures found in {FIXTURE_DIR}. Note .gitignore excludes *.ibt "
        "and needs the !tests/data/*.ibt exception.")


@pytest.mark.parametrize("path", fixture_paths(), ids=os.path.basename)
class TestFixtureIsScrubbed:

    def test_only_one_driver_listed(self, path):
        drivers = read_info(path).get("DriverInfo", {}).get("Drivers", []) or []
        assert len(drivers) == 1, (
            f"{len(drivers)} drivers listed — every other competitor's name and "
            "customer ID would be published")

    def test_driver_name_is_anonymous(self, path):
        for d in read_info(path)["DriverInfo"]["Drivers"]:
            assert d.get("UserName") in ALLOWED_NAMES

    def test_customer_ids_are_zeroed(self, path):
        info = read_info(path)
        assert info["DriverInfo"].get("DriverUserID") in (0, None)
        for d in info["DriverInfo"]["Drivers"]:
            assert d.get("UserID") in (0, None)

    def test_identity_fields_are_placeholders(self, path):
        for d in read_info(path)["DriverInfo"]["Drivers"]:
            for field in ("AbbrevName", "Initials", "TeamName"):
                if field in d:
                    assert d[field] in ALLOWED_NAMES, f"{field}={d[field]!r} not scrubbed"

    def test_unnecessary_sections_removed(self, path):
        present = set(read_info(path).keys())
        leaked = present & FORBIDDEN_SECTIONS
        assert not leaked, f"sections that may carry personal data remain: {leaked}"

    def test_no_identities_anywhere_in_the_binary(self, path):
        """Raw scan, in case a name survives outside the parsed structure."""
        with open(path, "rb") as f:
            blob = f.read().lower()
        # Any UserName line must name the placeholder driver
        text = blob[:200000].decode("latin-1", errors="replace")
        for value in re.findall(r"username:\s*(.+)", text):
            assert value.strip() in {n.lower() for n in ALLOWED_NAMES}

    def test_fixture_stays_small_enough_to_commit(self, path):
        mb = os.path.getsize(path) / 1024 / 1024
        assert mb < 10, (
            f"{mb:.1f}MB is too large for a committed fixture; trim laps with "
            "tools/make_test_fixture.py --laps")

    def test_fixture_is_analysable(self, path):
        """A fixture that cannot be analysed is worse than no fixture."""
        from tenths.analyzer import analyze
        data = analyze(path)
        assert data is not None
        assert len(data["valid_laps"]) >= 3, (
            "at least 3 valid laps are needed for corner variance")
        assert data["braking_zones"], "no braking zones detected"
