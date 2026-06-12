"""
Shared test fixtures for Tenths test suite.

Integration tests use real archived .ibt files. These tests are skipped
if the archive directory or specific files are not available (e.g., on CI).

Fixtures are session-scoped to avoid re-parsing 50-170MB .ibt files
for every individual test function.
"""

import os
import pytest

# Paths to real archived telemetry files for integration tests
TELEMETRY_ARCHIVE = r"c:\Users\justi\Documents\iRacing\telemetry\_archive"

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
