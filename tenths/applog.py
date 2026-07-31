"""
Tenths Logging
================
Durable, rotating log file plus optional console output.

The packaged application runs with ``console=False``, so ``print()`` output goes
nowhere. Without a log file a processing failure is completely invisible: the
tray icon looks healthy and the user simply never gets a report. That is also
what makes beta feedback useless — "it didn't work" with nothing to inspect.

Log location: ``%LOCALAPPDATA%\\Tenths\\logs\\tenths.log`` (see config.LOG_DIR).
The Inno installer already removes that folder on uninstall.

Usage:
    from tenths.applog import get_logger, configure_logging
    configure_logging()          # once, from an entry point
    log = get_logger(__name__)
    log.info("Processing %s", filename)
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from tenths.config import LOG_DIR

LOG_FILENAME = "tenths.log"

# Keep the log bounded — the tray can run for weeks
MAX_BYTES = 2_000_000
BACKUP_COUNT = 3

FILE_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
CONSOLE_FORMAT = "%(message)s"

_ROOT_NAME = "tenths"
_configured = False


def log_path(log_dir=None):
    """Full path to the active log file."""
    return os.path.join(log_dir or LOG_DIR, LOG_FILENAME)


def configure_logging(level=logging.INFO, console=None, log_dir=None, force=False):
    """Attach file (and optionally console) handlers to the 'tenths' logger.

    Safe to call more than once; handlers are only attached the first time unless
    ``force`` is set. Never raises: if the log directory cannot be created the
    application must still run, just without a log file.

    Args:
        level: logging level for the Tenths logger
        console: attach a console handler. Defaults to True when stdout exists,
                 which is the CLI case; the frozen tray app has no stdout.
        log_dir: override the log directory (used by tests)
        force: replace existing handlers

    Returns:
        The path to the log file, or None if file logging could not be set up.
    """
    global _configured

    logger = logging.getLogger(_ROOT_NAME)
    if _configured and not force:
        return getattr(logger, "_tenths_log_path", None)

    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    logger.setLevel(level)
    # Tenths owns this logger's output; don't also emit via the root logger
    logger.propagate = False

    if console is None:
        console = sys.stdout is not None

    resolved_path = None
    directory = log_dir or LOG_DIR
    try:
        os.makedirs(directory, exist_ok=True)
        resolved_path = os.path.join(directory, LOG_FILENAME)
        file_handler = RotatingFileHandler(
            resolved_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
            encoding="utf-8", delay=True,
        )
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except OSError:
        # No log file available (permissions, read-only volume). Keep running.
        resolved_path = None

    if console and sys.stdout is not None:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        stream_handler.setLevel(level)
        logger.addHandler(stream_handler)

    # A logger with no handlers warns on first use
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    logger._tenths_log_path = resolved_path
    _configured = True
    return resolved_path


def get_logger(name=None):
    """Return a child of the Tenths logger."""
    if not name or name == _ROOT_NAME:
        return logging.getLogger(_ROOT_NAME)
    if name.startswith(_ROOT_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_NAME}.{name}")


def reset_logging():
    """Detach handlers and allow reconfiguration. For tests."""
    global _configured
    logger = logging.getLogger(_ROOT_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    if hasattr(logger, "_tenths_log_path"):
        del logger._tenths_log_path
    _configured = False
