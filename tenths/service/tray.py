"""
Tenths System Tray Application
================================
Runs the Tenths watcher as a background service with a system tray icon.
No terminal window — just an icon in the taskbar notification area.

Usage:
    python -m tenths.cli tray
    # Or directly:
    python tenths/service/tray.py
"""

import os
import sys
import threading
import webbrowser
import glob
import winreg

import pystray
from PIL import Image

import tenths.config as cfg
from tenths.applog import get_logger
from tenths.service.watcher import TelemetryWatcher
from tenths.config import ICON_PATH, TELEMETRY_ROOT

log = get_logger(__name__)

# Registry key for startup
STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_KEY = "Tenths"


class TenthsTray:
    """System tray application for Tenths."""

    def __init__(self):
        self._watcher = None
        self._watcher_thread = None
        self._paused = False
        self._icon = None
        self._last_report = None

    def run(self):
        """Start the tray app. Blocks until user exits."""
        # Load icon
        icon_image = self._load_icon()

        # Create tray icon
        self._icon = pystray.Icon(
            name="Tenths",
            icon=icon_image,
            title="Tenths — Watching for sessions",
            menu=self._build_menu(),
        )

        # Start watcher in background thread
        self._start_watcher()

        # Run the tray icon (blocks on main thread)
        self._icon.run()

    def _build_menu(self):
        """Build the tray menu.

        Separated from `run()` so tests can construct it without starting the
        icon, which blocks. Nothing here is checked by Python at import time, so
        an unverified menu is a menu that only fails in front of a user.
        """
        return pystray.Menu(
            pystray.MenuItem("Open Last Report", self._open_last_report, default=True),
            pystray.MenuItem("Browse Sessions", self._open_index),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause Processing", self._toggle_pause,
                             checked=lambda item: self._paused),
            pystray.MenuItem("Metric Units (km/h)", self._toggle_units,
                             checked=lambda item: self._is_metric()),
            pystray.MenuItem("Start with Windows", self._toggle_startup,
                             checked=lambda item: self._is_startup_registered()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._exit),
        )

    def _load_icon(self):
        """Load the tray icon image."""
        if os.path.exists(ICON_PATH):
            return Image.open(ICON_PATH)
        else:
            # Fallback: generate a simple colored circle
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.ellipse([4, 4, 60, 60], fill=(0, 230, 118, 255))  # accent-green
            return img

    def _start_watcher(self):
        """Start the file watcher in a background thread."""
        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            return  # already running; never start a second observer

        # The watcher reports the finished report path once processing actually
        # completes, rather than the tray guessing immediately after dispatch.
        self._watcher = TelemetryWatcher(auto_open=False,
                                        on_complete=self._on_session_complete)
        self._watcher_thread = threading.Thread(target=self._watcher.start, daemon=True)
        self._watcher_thread.start()

    def _on_session_complete(self, report_path):
        """Called by the watcher once a session's report exists on disk."""
        self._last_report = report_path

    def _open_last_report(self, icon=None, item=None):
        """Open the most recent session report in the browser."""
        report = self._last_report or self._find_latest_report()
        if report and os.path.exists(report):
            webbrowser.open(f'file:///{report.replace(os.sep, "/")}')
        else:
            # Fallback: try to find any report
            report = self._find_latest_report()
            if report:
                webbrowser.open(f'file:///{report.replace(os.sep, "/")}')

    def _open_index(self, icon=None, item=None):
        """Open the master session index in the browser."""
        index_path = os.path.join(TELEMETRY_ROOT, "index.html")
        if os.path.exists(index_path):
            webbrowser.open(f'file:///{index_path.replace(os.sep, "/")}')

    def _find_latest_report(self):
        """Find the most recently modified session_report.html."""
        pattern = os.path.join(TELEMETRY_ROOT, "**", "session_report.html")
        reports = glob.glob(pattern, recursive=True)
        if not reports:
            return None
        return max(reports, key=os.path.getmtime)

    def _toggle_pause(self, icon=None, item=None):
        """Toggle processing pause state."""
        self._paused = not self._paused
        if self._paused:
            self._watcher.stop()
            self._icon.title = "Tenths — Paused"
        else:
            # Restart watcher
            self._start_watcher()
            self._icon.title = "Tenths — Watching for sessions"

    def _is_metric(self):
        """Whether metric display units are active.

        Read at call time rather than cached, so the menu tick always reflects
        what the next generated report will use.
        """
        return cfg.is_metric()

    def _toggle_units(self, icon=None, item=None):
        """Switch display units between imperial and metric.

        The tray is the one sanctioned runtime writer of `config.UNITS`. That
        value is normally resolved once at process start, but every display
        boundary calls `config.is_metric()` at the moment it formats a value, so
        assigning it here means the next processed session picks the change up
        without restarting Tenths. The watcher runs in a thread of this process,
        so there is nothing else to notify. See the units contract in
        `tenths/units.py`.

        Persist before applying. If the settings file cannot be written, nothing
        changes at all, so the menu tick can never disagree with what is on disk.
        """
        target = cfg.UNITS_IMPERIAL if cfg.is_metric() else cfg.UNITS_METRIC
        try:
            cfg.save_settings({'units': target})
        except OSError as exc:
            log.error("Could not save display units to %s: %s", cfg.SETTINGS_PATH, exc)
            self._notify_units("Units unchanged",
                               "Tenths could not write its settings file, so display "
                               "units were left as they are.")
            return

        cfg.UNITS = target
        labels = "km/h and °C" if target == cfg.UNITS_METRIC else "mph and °F"
        log.info("Display units set to %s (%s)", target, labels)
        self._notify_units(f"Units switched to {target}",
                           f"New reports will use {labels}. Reports already "
                           f"generated keep the units they were made with.")

    def _notify_units(self, title, message):
        """Confirm a units change. Nothing else visibly changes until the next
        session is processed, so silence would look like the click did nothing.
        """
        try:
            from tenths.service.notifier import SessionNotifier
            SessionNotifier().notify_info(title, message)
        except Exception as exc:
            # A missing toast must never take the tray down with it.
            log.warning("Could not show units notification: %s", exc)

    def _toggle_startup(self, icon=None, item=None):
        """Toggle 'Start with Windows' registry entry."""
        if self._is_startup_registered():
            self._unregister_startup()
        else:
            self._register_startup()

    def _is_startup_registered(self):
        """Check if Tenths is registered to start with Windows."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, STARTUP_REG_KEY)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            return False

    def _startup_command(self):
        """The command Windows should run at logon.

        In a frozen build sys.executable is Tenths.exe, which already starts the
        tray, so appending `-m tenths.cli tray` is meaningless. Running from
        source needs pythonw so no console window appears.
        """
        if getattr(sys, 'frozen', False):
            return f'"{sys.executable}"'
        python_exe = sys.executable.replace('python.exe', 'pythonw.exe')
        if not os.path.exists(python_exe):
            python_exe = sys.executable
        return f'"{python_exe}" -m tenths.cli tray'

    def _register_startup(self):
        """Add Tenths to Windows startup."""
        try:
            cmd = self._startup_command()

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, STARTUP_REG_KEY, 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
        except OSError:
            pass

    def _unregister_startup(self):
        """Remove Tenths from Windows startup."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, STARTUP_REG_KEY)
            winreg.CloseKey(key)
        except (FileNotFoundError, OSError):
            pass

    def _exit(self, icon=None, item=None):
        """Stop everything and exit."""
        if self._watcher:
            self._watcher.stop()
        self._icon.stop()


def main(argv=None):
    """Entry point for the tray application.

    The packaged build ships one executable, so this is also the only entry point
    a beta tester can reach. When arguments are present they are handed to the
    CLI instead of being ignored, which is what makes the documented
    `Tenths.exe config` work; with no arguments the tray starts as before.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if args:
        from tenths.config import attach_parent_console
        attach_parent_console()
        from tenths.cli import main as cli_main
        return cli_main(args)

    from tenths.config import configure_console
    from tenths.applog import configure_logging, get_logger
    configure_console()
    # The frozen tray has no console, so the log file is the only record.
    log_file = configure_logging()
    log = get_logger(__name__)
    log.info("Tenths tray starting (log: %s)", log_file)
    try:
        app = TenthsTray()
        app.run()
    except Exception:
        log.exception("Tray application terminated with an unhandled error")
        raise
    finally:
        log.info("Tenths tray stopped")


if __name__ == "__main__":
    main()
