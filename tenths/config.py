"""
Tenths Configuration
=====================
Centralized configuration with smart defaults.
All paths are auto-detected for the current user, overridable via environment variables.
"""

import os
import sys


def _find_iracing_telemetry():
    """Auto-detect the iRacing telemetry directory for the current user."""
    # Standard iRacing telemetry location
    docs = os.path.expanduser("~/Documents")
    default = os.path.join(docs, "iRacing", "telemetry")
    if os.path.isdir(default):
        return default
    # Fallback to Documents root if iRacing folder exists without telemetry subfolder
    iracing_dir = os.path.join(docs, "iRacing")
    if os.path.isdir(iracing_dir):
        os.makedirs(default, exist_ok=True)
        return default
    return default  # Return even if doesn't exist yet — iRacing will create it


def _find_package_root():
    """Find the Tenths package/resource root directory.

    Handles both running from source and from a PyInstaller frozen exe.
    In a frozen app, bundled resources live under sys._MEIPASS.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Paths ─────────────────────────────────────────────────────────────────────

# Telemetry root — where iRacing writes .ibt files
TELEMETRY_ROOT = os.environ.get('TENTHS_TELEMETRY_ROOT', _find_iracing_telemetry())

# Archive directory — processed .ibt files go here
ARCHIVE_DIR = os.path.join(TELEMETRY_ROOT, "_archive")

# Package root — where Tenths is installed
PACKAGE_ROOT = _find_package_root()

# Tracks directory — track map markdown files
TRACKS_DIR = os.environ.get('TENTHS_TRACKS_DIR', os.path.join(PACKAGE_ROOT, "tracks"))

# Assets directory — icons, images
ASSETS_DIR = os.path.join(PACKAGE_ROOT, "assets")

# Icon path
ICON_PATH = os.path.join(ASSETS_DIR, "tenths.ico")

# Downloads folder — for race result CSV auto-matching
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")

# ── Processing Settings ───────────────────────────────────────────────────────

# Minimum file size to process (below this is a false start)
MIN_SESSION_SIZE = 1_000_000  # 1MB

# Seconds of stability before processing
FILE_STABLE_SECONDS = 5

# ── Version ───────────────────────────────────────────────────────────────────

VERSION = "0.9.0"
