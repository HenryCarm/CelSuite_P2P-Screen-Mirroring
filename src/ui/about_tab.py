"""
About & Help tab for ScrcpyUltimateLink.
"""

from __future__ import annotations

import platform
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig
from src.constants import APP_NAME, APP_VERSION
from src.networking.adb import get_adb_version
from src.logger import get_logger
from src.ui.widgets.section_card import SectionCard

log = get_logger(__name__)


class AboutTab(QWidget):
    """About & Help tab with app info, setup guide, and system diagnostics."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)

        # ── App Info ──────────────────────────────────────────────────
        info_group = SectionCard(f"\u2728  {APP_NAME}")
        info_layout = QVBoxLayout()

        version_label = QLabel(f"Version: {APP_VERSION}")
        version_label.setObjectName("section-title")
        info_layout.addWidget(version_label)

        info_layout.addWidget(QLabel(
            "Wireless screen mirroring, remote control, and file transfer "
            "suite built on scrcpy + ADB."
        ))
        info_layout.addWidget(QLabel(
            "Instantly connects your Android phone to your PC over WiFi "
            "with zero USB cables needed."
        ))

        info_group.addLayout(info_layout)
        layout.addWidget(info_group)

        # ── Quick Setup Guide ─────────────────────────────────────────
        guide_group = SectionCard("\U0001f4d6  Quick Setup Guide")
        guide_layout = QVBoxLayout()

        steps = [
            "1. Connect your phone and PC to the same WiFi/hotspot network.",
            "2. On your phone, enable Developer Options and turn on Wireless Debugging.",
            "3. Open this app on your PC and tap 'Auto-Discover (Heartbeat)'.",
            "4. Open the companion app on your Android phone.",
            "5. The connection happens automatically! scrcpy will launch instantly.",
            "",
            "Alternative: Use 'Subnet Scan' if heartbeat discovery fails.",
            "Alternative: Pair via ADB first: adb pair <phone-ip>:<port>",
        ]
        for step in steps:
            if step:
                guide_layout.addWidget(QLabel(step))
            else:
                guide_layout.addWidget(QLabel(""))

        guide_group.addLayout(guide_layout)
        layout.addWidget(guide_group)

        # ── Shizuku Setup ─────────────────────────────────────────────
        shizuku_group = SectionCard("\U0001f511  Shizuku (Rootless ADB)")
        shizuku_layout = QVBoxLayout()
        shizuku_layout.addWidget(QLabel(
            "For Android apps requiring ADB commands without root:"
        ))
        shizuku_layout.addWidget(QLabel("1. Install Shizuku from Play Store."))
        shizuku_layout.addWidget(QLabel("2. Start Shizuku via Wireless Debugging."))
        shizuku_layout.addWidget(QLabel(
            "3. The companion app will use 'rish' to execute ADB commands."
        ))
        shizuku_group.addLayout(shizuku_layout)
        layout.addWidget(shizuku_group)

        # ── System Diagnostics ────────────────────────────────────────
        diag_group = SectionCard("\U0001f4bb  System Diagnostics")
        diag_layout = QVBoxLayout()

        diag_layout.addWidget(QLabel(f"Python: {sys.version.split()[0]}"))

        try:
            import PySide6
            from PySide6.QtCore import qVersion
            diag_layout.addWidget(QLabel(f"Qt: {qVersion()}"))
            diag_layout.addWidget(QLabel(f"PySide6: {PySide6.__version__}"))
        except ImportError:
            diag_layout.addWidget(QLabel("Qt: unknown"))

        diag_layout.addWidget(QLabel(
            f"OS: {platform.system()} {platform.release()}"
        ))
        diag_layout.addWidget(QLabel(
            f"Architecture: {platform.machine()}"
        ))

        # ADB version
        adb_ver = get_adb_version(self._config)
        diag_layout.addWidget(QLabel(f"ADB: {adb_ver}"))

        # scrcpy version
        import subprocess
        scrcpy_bin = self._config.get("scrcpy_bin", "scrcpy")
        try:
            result = subprocess.run(
                [scrcpy_bin, "--version"],
                capture_output=True, text=True, timeout=3,
            )
            scrcpy_ver = result.stdout.strip().split("\n")[0] if result.stdout else "unknown"
        except (FileNotFoundError, subprocess.SubprocessError):
            scrcpy_ver = "Not installed"
        diag_layout.addWidget(QLabel(f"scrcpy: {scrcpy_ver}"))

        diag_group.addLayout(diag_layout)
        layout.addWidget(diag_group)

        # ── Credits ───────────────────────────────────────────────────
        credits_group = SectionCard("\U0001f4dd  Credits")
        credits_layout = QVBoxLayout()
        credits_layout.addWidget(QLabel(f"Developed by Henry"))
        credits_layout.addWidget(QLabel("Built with PySide6, scrcpy, and ADB"))
        credits_layout.addWidget(QLabel(
            "scrcpy is open-source: https://github.com/Genymobile/scrcpy"
        ))
        credits_group.addLayout(credits_layout)
        layout.addWidget(credits_group)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
