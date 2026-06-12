"""
Shared test fixtures for Tenths test suite.

Provides paths to archived .ibt files for integration testing
and helper functions for synthetic data generation.
"""

import os
import pytest

# Paths to real archived telemetry files for integration tests
TELEMETRY_ARCHIVE = r"c:\Users\justi\Documents\iRacing\telemetry\_archive"

# Known good test files
WINTON_RACE_IBT = os.path.join(TELEMETRY_ARCHIVE, "bmwm2csr_winton national 2026-06-06 22-26-36.ibt")
MIDOHIO_PRACTICE_IBT = os.path.join(TELEMETRY_ARCHIVE, "bmwm4evogt4_midohio full 2026-06-02 20-48-57.ibt")


@pytest.fixture
def winton_race_data():
    """Analyze the Winton race session and return the data dict."""
    from tenths.analyzer import analyze
    data = analyze(WINTON_RACE_IBT)
    assert data is not None, f"Failed to analyze {WINTON_RACE_IBT}"
    return data


@pytest.fixture
def midohio_practice_data():
    """Analyze the Mid-Ohio practice session and return the data dict."""
    from tenths.analyzer import analyze
    data = analyze(MIDOHIO_PRACTICE_IBT)
    assert data is not None, f"Failed to analyze {MIDOHIO_PRACTICE_IBT}"
    return data


@pytest.fixture
def winton_file_info():
    """File info dict for the Winton race session."""
    from tenths.process import parse_filename
    return parse_filename(WINTON_RACE_IBT)


@pytest.fixture
def midohio_file_info():
    """File info dict for the Mid-Ohio practice session."""
    from tenths.process import parse_filename
    return parse_filename(MIDOHIO_PRACTICE_IBT)


@pytest.fixture
def winton_track_map():
    """Load the Winton track map."""
    from tenths.track_map import load_track_map
    return load_track_map("winton_national")


@pytest.fixture
def midohio_track_map():
    """Load the Mid-Ohio track map."""
    from tenths.track_map import load_track_map
    return load_track_map("midohio_full")
