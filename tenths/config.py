"""
Tenths Configuration
=====================
Centralized configuration with smart defaults.
All paths are auto-detected for the current user, overridable via environment variables.
"""

import json
import os
import sys

# Problems encountered while loading configuration. This module cannot import
# applog (applog imports config), so entry points drain this list once logging
# is up. A bad settings file must never be silent.
CONFIG_WARNINGS = []


def configure_console():
    """Reconfigure stdout/stderr to UTF-8 so Unicode (→, ✓, °, etc.) prints on
    stock Windows consoles (default cp1252) without UnicodeEncodeError.

    Safe to call from any entry point. Guarded for frozen/no-console builds
    where stdout may be None, and for streams lacking reconfigure().
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def attach_parent_console():
    """Attach the invoking console so a windowed build can print.

    The packaged exe is built with `console=False`, so `sys.stdout` is None and
    anything printed is discarded. That silently breaks the documented
    `Tenths.exe config` command: a tester runs it from cmd, sees nothing, and has
    no way to tell whether it worked. AttachConsole(ATTACH_PARENT_PROCESS) hands
    us the console that launched us so output lands where the user is looking.

    Returns True when output is usable afterwards. Never raises; if there is no
    parent console (a double-clicked exe) the caller still runs, it just cannot
    print, which is why callers should also log.
    """
    if not getattr(sys, 'frozen', False):
        return sys.stdout is not None

    try:
        import ctypes
        ATTACH_PARENT_PROCESS = -1
        if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            return sys.stdout is not None
    except (ImportError, AttributeError, OSError):
        return sys.stdout is not None

    attached = False
    for name, stream_name in (("stdout", "CONOUT$"), ("stderr", "CONOUT$")):
        try:
            stream = open(stream_name, "w", encoding="utf-8", errors="replace",
                          buffering=1)
        except OSError:
            continue
        setattr(sys, name, stream)
        attached = True
    return attached


def _documents_dir():
    """Resolve the user's Documents folder the way iRacing itself does.

    iRacing uses the Windows Known Folder API, which follows redirection. Simply
    joining %USERPROFILE% and "Documents" does not: when OneDrive folder backup
    is enabled, Documents moves to %USERPROFILE%\\OneDrive\\Documents, and the
    naive path points at a directory iRacing never writes to. Moving Documents to
    another drive has the same effect.

    Order: Known Folder API, then the registry value it is backed by, then the
    naive path as a last resort.
    """
    # 1. SHGetKnownFolderPath(FOLDERID_Documents)
    try:
        import ctypes
        import ctypes.wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.wintypes.DWORD),
                        ("Data2", ctypes.wintypes.WORD),
                        ("Data3", ctypes.wintypes.WORD),
                        ("Data4", ctypes.c_byte * 8)]

        guid = _GUID()
        ctypes.windll.ole32.CLSIDFromString(
            ctypes.c_wchar_p("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"), ctypes.byref(guid))
        buf = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(buf)) == 0:
            path = buf.value
            ctypes.windll.ole32.CoTaskMemFree(buf)
            if path and os.path.isdir(path):
                return os.path.normpath(path)
    except (ImportError, AttributeError, OSError, ValueError):
        pass

    # 2. Registry (same source the API reads, useful if the call above fails)
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, "Personal")
        finally:
            winreg.CloseKey(key)
        if value and os.path.isdir(value):
            return os.path.normpath(value)
    except (ImportError, OSError):
        pass

    # 3. Last resort
    return os.path.normpath(os.path.join(os.path.expanduser("~"), "Documents"))


def iracing_dir():
    """The iRacing data folder (<Documents>/iRacing). May not exist."""
    return os.path.join(_documents_dir(), "iRacing")


def _find_iracing_telemetry():
    """Best-known iRacing telemetry directory. Never creates anything.

    Creating the directory here is what turned a wrong guess into a silent
    permanent failure: the watcher reported that it was monitoring a folder
    iRacing would never write to. Whether the path is usable is decided by the
    caller, which can tell the user when it is not.
    """
    return os.path.join(iracing_dir(), "telemetry")


def _find_package_root():
    """Find the Tenths package/resource root directory.

    Handles both running from source and from a PyInstaller frozen exe.
    In a frozen app, bundled resources live under sys._MEIPASS.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Paths ─────────────────────────────────────────────────────────────────────

def _settings_path():
    """Location of the user settings file."""
    override = os.environ.get('TENTHS_SETTINGS')
    if override:
        return override
    base = os.environ.get('LOCALAPPDATA')
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "Tenths", "settings.json")


SETTINGS_PATH = _settings_path()


def load_settings(path=None):
    """Read the settings file. Returns {} when absent or unreadable.

    A malformed file must not stop Tenths from starting; the problem is recorded
    in CONFIG_WARNINGS and logged by the entry point instead.
    """
    target = path or SETTINGS_PATH
    if not os.path.isfile(target):
        return {}
    try:
        with open(target, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            CONFIG_WARNINGS.append(
                f"Settings file {target} does not contain a JSON object; ignoring it.")
            return {}
        return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        CONFIG_WARNINGS.append(
            f"Could not read the settings file {target}: {exc}. Using defaults.")
        return {}


def save_settings(updates, path=None):
    """Merge updates into the settings file and write it back.

    Returns the path written. Raises OSError if it cannot be written, so a CLI
    can tell the user rather than silently doing nothing.
    """
    target = path or SETTINGS_PATH
    current = load_settings(target)
    current.update(updates)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(current, f, indent=2)
    return target


SETTINGS = load_settings()


def _resolve_telemetry_root():
    """Telemetry root, in precedence order.

    1. TENTHS_TELEMETRY_ROOT environment variable (development and overrides)
    2. `telemetry_root` in the settings file (what a user can actually set)
    3. Auto-detection from the Documents known folder

    An unusual install needs a way to point Tenths at its telemetry folder that
    does not involve setting an environment variable, which no installed user
    will do.
    """
    env = os.environ.get('TENTHS_TELEMETRY_ROOT')
    if env:
        return os.path.normpath(env)

    configured = SETTINGS.get('telemetry_root')
    if configured:
        configured = os.path.normpath(str(configured))
        if not os.path.isdir(configured):
            CONFIG_WARNINGS.append(
                f"The configured telemetry_root does not exist: {configured}. "
                f"Fix it with `tenths config --telemetry-root <path>`.")
        return configured

    return _find_iracing_telemetry()


# Telemetry root — where iRacing writes .ibt files
TELEMETRY_ROOT = _resolve_telemetry_root()

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


def _default_app_data_dir():
    """Per-user application data directory (%LOCALAPPDATA%\\Tenths)."""
    base = os.environ.get('LOCALAPPDATA')
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "Tenths")


# Application data — logs live here. The installer removes this on uninstall.
APP_DATA_DIR = os.environ.get('TENTHS_APP_DATA', _default_app_data_dir())

# Log directory. The packaged app runs without a console, so the log file is the
# only way a user (or a beta tester filing a report) can see what went wrong.
LOG_DIR = os.environ.get('TENTHS_LOG_DIR', os.path.join(APP_DATA_DIR, "logs"))

# ── Processing Settings ───────────────────────────────────────────────────────

# Minimum file size to process (below this is a false start)
MIN_SESSION_SIZE = 1_000_000  # 1MB

# Seconds of stability before processing
FILE_STABLE_SECONDS = 5

# ── Version ───────────────────────────────────────────────────────────────────

VERSION = "0.9.0"
