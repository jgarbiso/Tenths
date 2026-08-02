"""
Shared test fixtures for Tenths test suite.

Integration tests use real archived .ibt files. These tests are skipped
if the archive directory or specific files are not available (e.g., on CI).

Fixtures are session-scoped to avoid re-parsing 50-170MB .ibt files
for every individual test function.

Safety: an autouse fixture replaces winreg with an in-memory fake for every
test, so no test can create, modify or delete a real HKCU value. Startup
registration is a user setting — a test run must never disturb it.
"""

import os
import pytest

# Committed test fixtures: real telemetry, trimmed to a few laps and with every
# driver identity replaced (see tools/make_test_fixture.py). These ship with the
# repo so integration tests run anywhere.
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# The full sessions on the developer's machine. Preferred when present because
# they carry more laps; the committed fixtures are used otherwise.
# TENTHS_TEST_ARCHIVE overrides the location; set it to a nonexistent path to
# force the committed fixtures and reproduce what CI sees.
TELEMETRY_ARCHIVE = os.environ.get(
    "TENTHS_TEST_ARCHIVE",
    os.path.join(os.path.expanduser("~"), "Documents", "iRacing", "telemetry", "_archive"),
)


def _telemetry_file(filename):
    """Full archived session if available, else the committed trimmed fixture."""
    full = os.path.join(TELEMETRY_ARCHIVE, filename)
    if os.path.exists(full):
        return full
    return os.path.join(FIXTURE_DIR, filename)

# Known good test files
WINTON_RACE_IBT = _telemetry_file("bmwm2csr_winton national 2026-06-06 22-26-36.ibt")
MIDOHIO_PRACTICE_IBT = _telemetry_file("bmwm4evogt4_midohio full 2026-06-02 20-48-57.ibt")

# Skip markers for integration tests
requires_winton = pytest.mark.skipif(
    not os.path.exists(WINTON_RACE_IBT),
    reason=f"Winton .ibt file not found at {WINTON_RACE_IBT}"
)
requires_midohio = pytest.mark.skipif(
    not os.path.exists(MIDOHIO_PRACTICE_IBT),
    reason=f"Mid-Ohio .ibt file not found at {MIDOHIO_PRACTICE_IBT}"
)


@pytest.fixture(scope="session")
def winton_race_data():
    """Analyze the Winton race session. Session-scoped (parsed once)."""
    if not os.path.exists(WINTON_RACE_IBT):
        pytest.skip(f"File not found: {WINTON_RACE_IBT}")
    from tenths.analyzer import analyze
    data = analyze(WINTON_RACE_IBT)
    assert data is not None, f"Failed to analyze {WINTON_RACE_IBT}"
    return data


@pytest.fixture(scope="session")
def midohio_practice_data():
    """Analyze the Mid-Ohio practice session. Session-scoped (parsed once)."""
    if not os.path.exists(MIDOHIO_PRACTICE_IBT):
        pytest.skip(f"File not found: {MIDOHIO_PRACTICE_IBT}")
    from tenths.analyzer import analyze
    data = analyze(MIDOHIO_PRACTICE_IBT)
    assert data is not None, f"Failed to analyze {MIDOHIO_PRACTICE_IBT}"
    return data


@pytest.fixture(scope="session")
def winton_file_info():
    """File info dict for the Winton race session."""
    if not os.path.exists(WINTON_RACE_IBT):
        pytest.skip(f"File not found: {WINTON_RACE_IBT}")
    from tenths.process import parse_filename
    return parse_filename(WINTON_RACE_IBT)


@pytest.fixture(scope="session")
def midohio_file_info():
    """File info dict for the Mid-Ohio practice session."""
    if not os.path.exists(MIDOHIO_PRACTICE_IBT):
        pytest.skip(f"File not found: {MIDOHIO_PRACTICE_IBT}")
    from tenths.process import parse_filename
    return parse_filename(MIDOHIO_PRACTICE_IBT)


@pytest.fixture(scope="session")
def winton_track_map():
    """Load the Winton track map."""
    from tenths.track_map import load_track_map
    return load_track_map("winton_national")


@pytest.fixture(scope="session")
def midohio_track_map():
    """Load the Mid-Ohio track map."""
    from tenths.track_map import load_track_map
    return load_track_map("midohio_full")


# ─── Registry isolation ───────────────────────────────────────────────────────

class _FakeRegistryKey:
    """Handle returned by the fake OpenKey."""

    def __init__(self, registry, subkey, access):
        self.registry = registry
        self.subkey = subkey
        self.access = access
        self.closed = False


class FakeRegistry:
    """In-memory stand-in for the winreg subset used by tray.py.

    Mirrors the real API closely enough to exercise the production code paths
    (including FileNotFoundError on a missing value and a write to a key opened
    read-only) without touching the machine.
    """

    HKEY_CURRENT_USER = "HKEY_CURRENT_USER"
    KEY_READ = 0x20019
    KEY_SET_VALUE = 0x0002
    REG_SZ = 1

    def __init__(self, initial=None):
        self.values = dict(initial or {})
        self.open_count = 0
        self.close_count = 0
        self.fail_on_set = False
        self.fail_on_open = False

    def OpenKey(self, root, subkey, reserved=0, access=0):
        if self.fail_on_open:
            raise OSError("access denied")
        self.open_count += 1
        return _FakeRegistryKey(self, subkey, access)

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(2, "The system cannot find the file specified", name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, value_type, value):
        if self.fail_on_set:
            raise OSError("access denied")
        if not key.access & self.KEY_SET_VALUE:
            raise PermissionError("key was not opened for writing")
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(2, "The system cannot find the file specified", name)
        del self.values[name]

    def CloseKey(self, key):
        key.closed = True
        self.close_count += 1


@pytest.fixture
def fake_registry(monkeypatch):
    """Replace winreg in the tray module with an inspectable in-memory fake."""
    from tenths.service import tray
    fake = FakeRegistry()
    monkeypatch.setattr(tray, "winreg", fake)
    return fake


@pytest.fixture(autouse=True)
def _never_touch_real_registry(monkeypatch, request):
    """Guard: no test may reach the real registry.

    Tests that need to inspect registry state request `fake_registry`, which
    installs its own instance; this fixture then steps aside.
    """
    if "fake_registry" in request.fixturenames:
        return
    try:
        from tenths.service import tray
    except Exception:
        return  # tray deps unavailable; nothing to guard
    monkeypatch.setattr(tray, "winreg", FakeRegistry())


@pytest.fixture(autouse=True)
def _never_write_track_maps_into_the_repo(monkeypatch, tmp_path_factory):
    """Guard: auto-generated track maps must never land in the working tree.

    Any test that exercises the analyse/process path for a track with no
    landmark entry triggers `write_skeleton_track_map()`. Its default target is
    `config.USER_TRACKS_DIR`; redirecting that per-test keeps the repository and
    the developer's real app-data folder clean.

    Before this guard, `tests/test_process_per_session.py` created
    `tracks/test_track.md` in the repo on every run — it was staged by a
    `git add -A` and only caught by manual inspection.
    """
    target = str(tmp_path_factory.mktemp("user_tracks"))
    try:
        from tenths import config
        from tenths import track_map
    except Exception:
        return

    real = config.USER_TRACKS_DIR
    monkeypatch.setattr(config, "USER_TRACKS_DIR", target, raising=False)

    # Keep the read path in step with the write path, so a test that generates a
    # map can also load it back. TRACK_MAPS_DIRS is built at import time, so
    # patching config alone would leave reads pointing at the real directory.
    monkeypatch.setattr(
        track_map, "TRACK_MAPS_DIRS",
        [target if d == real else d for d in track_map.TRACK_MAPS_DIRS],
        raising=False,
    )


# ─── Synthetic telemetry (machine independent) ────────────────────────────────

@pytest.fixture(scope="session")
def synthetic_session(tmp_path_factory):
    """Build a synthetic .ibt once per test session and return its ground truth.

    Unlike the real-.ibt fixtures this runs anywhere, and every apex speed and
    lap time is known exactly rather than merely plausible.
    """
    from synthetic_ibt import build_ibt, default_test_corners

    path = tmp_path_factory.mktemp("synthetic") / "testcar_testcircuit 2026-07-29 20-00-00.ibt"
    return build_ibt(str(path), default_test_corners(), laps=6, track_length_m=2000.0)


@pytest.fixture(scope="session")
def synthetic_data(synthetic_session):
    """analyze() output for the synthetic session."""
    from tenths.analyzer import analyze
    data = analyze(synthetic_session["path"])
    assert data is not None, "analyze() failed on the synthetic .ibt"
    return data


@pytest.fixture(scope="session")
def synthetic_file_info(synthetic_session):
    from tenths.process import parse_filename
    return parse_filename(synthetic_session["path"])
