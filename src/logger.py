"""
Centralized logging for ScrcpyUltimateLink.

Provides a single ``get_logger()`` function that returns a module-level
logger, plus a Qt-compatible handler that emits ``log_message`` signals
so the GUI log panel updates from any thread safely.

Usage::

    from src.logger import get_logger
    log = get_logger(__name__)
    log.info("Connected to %s", phone_ip)
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from src.constants import LOG_FILE

# ── Qt Signal Bridge ──────────────────────────────────────────────────────────

class _QtLogSignalBridge(QObject):
    """Singleton QObject that emits a signal for every log record."""
    log_message = Signal(str)

_bridge: Optional[_QtLogSignalBridge] = None


def get_signal_bridge() -> _QtLogSignalBridge:
    """Return (or create) the global Qt log signal bridge."""
    global _bridge
    if _bridge is None:
        _bridge = _QtLogSignalBridge()
    return _bridge


# ── Qt Log Handler ────────────────────────────────────────────────────────────

class QtSignalHandler(logging.Handler):
    """
    Logging handler that emits formatted log lines via a Qt signal.

    This makes it safe to update a ``QTextEdit`` from any thread — the
    signal/slot mechanism handles the cross-thread dispatch.
    """

    def __init__(self) -> None:
        super().__init__()
        self._bridge = get_signal_bridge()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._bridge.log_message.emit(msg)
        except RuntimeError:
            # Bridge may have been garbage-collected during shutdown
            pass


# ── Logger Setup ──────────────────────────────────────────────────────────────

_root_configured = False
_log_file_path: str = LOG_FILE
_file_logging_enabled: bool = True

# External callback for non-Qt consumers (e.g., heartbeat_listener standalone)
_external_callback: Optional[Callable[[str], None]] = None


def set_external_callback(callback: Optional[Callable[[str], None]]) -> None:
    """Set an external callback that receives formatted log lines."""
    global _external_callback
    _external_callback = callback


def configure(
    log_file: str = LOG_FILE,
    level: int = logging.DEBUG,
    file_logging: bool = True,
    console: bool = True,
) -> None:
    """
    Configure the root ``scrcpy`` logger.

    Call once at application startup before any ``get_logger()`` calls.
    """
    global _root_configured, _log_file_path, _file_logging_enabled
    _log_file_path = log_file
    _file_logging_enabled = file_logging

    root = logging.getLogger("scrcpy")
    root.setLevel(level)

    # Avoid duplicate handlers on re-configure
    root.handlers.clear()

    fmt = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] %(levelname)-5s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. File handler (rotating, max 1 MB, 3 backups)
    if file_logging:
        try:
            fh = RotatingFileHandler(
                log_file, maxBytes=1_048_576, backupCount=3, encoding="utf-8",
            )
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            pass  # Can't write log file — non-fatal, continue

    # 2. Console handler
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    # 3. Qt signal handler (for GUI log panel)
    qt_handler = QtSignalHandler()
    qt_handler.setLevel(logging.DEBUG)
    qt_handler.setFormatter(fmt)
    root.addHandler(qt_handler)

    _root_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger under the ``scrcpy`` namespace.

    If ``configure()`` hasn't been called yet, applies sensible defaults.
    """
    if not _root_configured:
        configure()
    return logging.getLogger(f"scrcpy.{name}")
