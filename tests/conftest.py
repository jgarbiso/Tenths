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

# Root of the archived telemetry used by integration tests.
# Override with TENTHS_TEST_ARCHIVE to run on another machine or in CI.
TELEMETRY_ARCHIVE = os.environ.get(
    "TENTHS_TEST_ARCHIVE",
    os.path.join(os.path.expanduser("~"), "Documents", "iRacing", "telemetry", "_archive"),
)

# Known good test files
WINTON_RACE_IBT = os.path.join(TELEMETRY_ARCHIVE, "bmwm2csr_winton national 2026-06-06 22-26-36.ibt")
MIDOHIO_PRACTICE_IBT = os.path.join(TELEMETRY_ARCHIVE, "bmwm4evogt4_midohio full 2026-06-02 20-48-57.ibt")

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
