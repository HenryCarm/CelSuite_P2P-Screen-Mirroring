"""
SVG icon system for CelSuite desktop (PySide6).

Why this exists: emoji in button/sidebar labels render as tofu boxes
(□□) on systems without a color-emoji font — notably Windows Nuitka
bundles and many Linux setups. These inline-friendly SVG line icons
render through QtSvg at any size and always look sharp.

Icons live in ``src/resources/icons/*.svg`` (also bundled by Nuitka via
``--include-data-dir``). Use :func:`icon` / :func:`set_button_icon`.

NOTE: Nuitka/CI must NOT exclude ``PySide6.QtSvg`` or icons go blank.
"""

from __future__ import annotations

import os
from functools import lru_cache

from PySide6.QtGui import QIcon, QPixmap

try:
    from PySide6 import QtSvg  # noqa: F401 (forces Nuitka to bundle SVG support)
except ImportError:
    pass

from src.constants import APP_DIR


def _search_dirs() -> list[str]:
    cands = [
        os.path.join(APP_DIR, "src", "resources", "icons"),
        os.path.join(APP_DIR, "resources", "icons"),
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "resources", "icons",
        ),
    ]
    try:
        import sys

        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            cands.append(os.path.join(exe_dir, "src", "resources", "icons"))
            cands.append(os.path.join(exe_dir, "resources", "icons"))
    except Exception:
        pass
    return cands


@lru_cache(maxsize=1)
def icons_dir() -> str:
    for d in _search_dirs():
        if os.path.isdir(d):
            return d
    return ""


@lru_cache(maxsize=64)
def _icon_path(name: str) -> str:
    d = icons_dir()
    p = os.path.join(d, f"{name}.svg") if d else ""
    return p if p and os.path.isfile(p) else ""


def available(name: str) -> bool:
    """True if the named SVG icon exists on disk."""
    return bool(_icon_path(name))


def icon(name: str) -> QIcon:
    """Return a QIcon for *name*, or an empty QIcon if missing."""
    p = _icon_path(name)
    return QIcon(p) if p else QIcon()


def pixmap(name: str, size: int = 24) -> QPixmap:
    """Return a QPixmap for *name* scaled to *size*, or null pixmap."""
    p = _icon_path(name)
    if not p:
        return QPixmap()
    pm = QPixmap(p)
    if pm.isNull():
        return pm
    return pm.scaled(
        size, size,
        __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AspectRatioMode.KeepAspectRatio,
        __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.TransformationMode.SmoothTransformation,
    )


def set_button_icon(button, name: str, size: int = 18) -> None:
    """Attach an SVG icon to a QPushButton/AnimatedButton (no-op if missing)."""
    try:
        ico = icon(name)
        if not ico.isNull():
            button.setIcon(ico)
            button.setIconSize(
                __import__("PySide6.QtCore", fromlist=["QSize"]).QSize(size, size)
            )
    except Exception:
        pass


# Sidebar tab → icon name mapping (single source of truth).
SIDEBAR_ICONS: dict[str, str] = {
    "Mirror Phone": "phone",
    "Control PC": "game",
    "Mirror PC": "monitor",
    "Phone Storage": "folder",
    "File Transfer": "transfer",
    "Logs": "logs",
    "Settings": "settings",
    "About": "about",
}
