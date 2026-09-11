"""
Settings tab for CelStudio Scrcpy Heartbeat.

Provides network, binary path, screenshot directory, and the
CelStudio Liquid Glass & Wallpaper Engine configuration.
"""

from __future__ import annotations

import glob
import os
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig
from src.constants import (
    APP_DIR,
    DEFAULT_ADB_PORT,
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_HEARTBEAT_PORT,
    DEFAULT_TCP_TRANSFER_PORT,
    DEFAULT_WALLPAPER,
)
from src.logger import get_logger
from src.ui.animations import AnimatedButton
from src.ui.widgets.section_card import SectionCard

log = get_logger(__name__)

_linux_wp_dir = "/home/henry/Documents/Projects/Python/.png"
OFFICIAL_WALLPAPERS_DIR = _linux_wp_dir if os.path.isdir(_linux_wp_dir) else os.path.join(APP_DIR, "wallpapers")


class SettingsTab(QWidget):
    """Application settings with grouped configuration sections and CelStudio Theme controls."""

    def __init__(
        self,
        config: AppConfig,
        on_theme_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._on_theme_changed = on_theme_changed
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settings-scroll")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        title = QLabel("🎨  CelStudio Settings")
        title.setObjectName("title")
        layout.addWidget(title)

        # ── 1. CelStudio Liquid Glass & Wallpaper Engine ──────────────
        theme_group = SectionCard("✨  CelStudio Theme & Glass Engine")
        theme_layout = QVBoxLayout()
        theme_layout.setSpacing(14)

        # Wallpaper Dropdown & Browse
        wp_label_row = QHBoxLayout()
        wp_label_row.addWidget(QLabel("Background Wallpaper (CelWeave):"))
        theme_layout.addLayout(wp_label_row)

        wp_row = QHBoxLayout()
        self._wp_combo = QComboBox()
        self._populate_wallpapers()
        self._wp_combo.currentIndexChanged.connect(self._on_wallpaper_selected)
        wp_row.addWidget(self._wp_combo, 3)

        wp_browse = AnimatedButton("Browse…")
        wp_browse.clicked.connect(self._browse_wallpaper)
        wp_row.addWidget(wp_browse, 1)
        theme_layout.addLayout(wp_row)

        # Liquid Glass Transparency Slider
        glass_pct = int(float(self._config.get("glass_opacity", 0.65)) * 100)
        self._glass_lbl = QLabel(f"Liquid Glass Opacity: {glass_pct}%")
        self._glass_lbl.setStyleSheet("font-weight: 600;")
        theme_layout.addWidget(self._glass_lbl)

        glass_row = QHBoxLayout()
        self._glass_slider = QSlider(Qt.Orientation.Horizontal)
        self._glass_slider.setRange(15, 100)
        self._glass_slider.setValue(glass_pct)
        self._glass_slider.valueChanged.connect(self._on_glass_changed)
        glass_row.addWidget(self._glass_slider)
        theme_layout.addLayout(glass_row)

        # Dark Overlay Tint Slider
        tint_pct = int(float(self._config.get("wallpaper_tint_opacity", 0.70)) * 100)
        self._tint_lbl = QLabel(f"Wallpaper Dark Tint: {tint_pct}%")
        self._tint_lbl.setStyleSheet("font-weight: 600;")
        theme_layout.addWidget(self._tint_lbl)

        tint_row = QHBoxLayout()
        self._tint_slider = QSlider(Qt.Orientation.Horizontal)
        self._tint_slider.setRange(10, 95)
        self._tint_slider.setValue(tint_pct)
        self._tint_slider.valueChanged.connect(self._on_tint_changed)
        tint_row.addWidget(self._tint_slider)
        theme_layout.addLayout(tint_row)

        theme_group.addLayout(theme_layout)
        layout.addWidget(theme_group)

        # ── 2. Network Ports ───────────────────────────────────────────
        ports_group = SectionCard("🌐  Network Ports")
        ports_layout = QVBoxLayout()

        self._port_widgets: dict[str, QSpinBox] = {}
        port_defs = [
            ("heartbeat_port", "Heartbeat Port (Phone → PC)", DEFAULT_HEARTBEAT_PORT),
            ("discovery_port", "Discovery Port (PC Broadcast)", DEFAULT_DISCOVERY_PORT),
            ("adb_port", "ADB TCP Port", DEFAULT_ADB_PORT),
            ("tcp_transfer_port", "File Transfer TCP Port", DEFAULT_TCP_TRANSFER_PORT),
        ]

        for key, label_text, default in port_defs:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            spin = QSpinBox()
            spin.setRange(1024, 65535)
            spin.setValue(self._config.get(key, default))
            spin.valueChanged.connect(lambda v, k=key: self._save_port(k, v))
            row.addWidget(spin)
            ports_layout.addLayout(row)
            self._port_widgets[key] = spin

        ports_group.addLayout(ports_layout)
        layout.addWidget(ports_group)

        # ── 3. Binary Paths ────────────────────────────────────────────
        bins_group = SectionCard("🔧  Binary Paths")
        bins_layout = QVBoxLayout()

        # scrcpy
        scrcpy_row = QHBoxLayout()
        scrcpy_row.addWidget(QLabel("scrcpy Binary:"))
        self._scrcpy_input = QLineEdit(self._config.get("scrcpy_bin", "scrcpy"))
        self._scrcpy_input.textChanged.connect(
            lambda t: self._config.__setitem__("scrcpy_bin", t)
        )
        scrcpy_browse = AnimatedButton("Browse…")
        scrcpy_browse.clicked.connect(
            lambda: self._browse_binary(self._scrcpy_input, "scrcpy_bin")
        )
        scrcpy_row.addWidget(self._scrcpy_input)
        scrcpy_row.addWidget(scrcpy_browse)
        bins_layout.addLayout(scrcpy_row)

        # adb
        adb_row = QHBoxLayout()
        adb_row.addWidget(QLabel("ADB Binary:"))
        self._adb_input = QLineEdit(self._config.get("adb_bin", "adb"))
        self._adb_input.textChanged.connect(
            lambda t: self._config.__setitem__("adb_bin", t)
        )
        adb_browse = AnimatedButton("Browse…")
        adb_browse.clicked.connect(
            lambda: self._browse_binary(self._adb_input, "adb_bin")
        )
        adb_row.addWidget(self._adb_input)
        adb_row.addWidget(adb_browse)
        bins_layout.addLayout(adb_row)

        bins_group.addLayout(bins_layout)
        layout.addWidget(bins_group)

        # ── 4. Directories ─────────────────────────────────────────────
        dirs_group = SectionCard("📂  Directories")
        dirs_layout = QVBoxLayout()

        ss_row = QHBoxLayout()
        ss_row.addWidget(QLabel("Screenshot Save Directory:"))
        self._ss_dir_input = QLineEdit(
            self._config.get("screenshot_dir", "")
        )
        self._ss_dir_input.setPlaceholderText("~/Pictures/ScrcpyUltimateLink/ (default)")
        self._ss_dir_input.textChanged.connect(
            lambda t: self._config.__setitem__("screenshot_dir", t)
        )
        ss_browse = AnimatedButton("Browse…")
        ss_browse.clicked.connect(self._browse_ss_dir)
        ss_row.addWidget(self._ss_dir_input)
        ss_row.addWidget(ss_browse)
        dirs_layout.addLayout(ss_row)
        dirs_group.addLayout(dirs_layout)
        layout.addWidget(dirs_group)

        # ── 5. Reset ───────────────────────────────────────────────────
        reset_btn = AnimatedButton("🔄  Reset All Settings to Defaults")
        reset_btn.setObjectName("action-danger")
        reset_btn.clicked.connect(self._reset_all)
        layout.addWidget(reset_btn)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _populate_wallpapers(self) -> None:
        self._wp_combo.clear()
        current_wp = self._config.get("wallpaper_path", DEFAULT_WALLPAPER)
        
        wallpaper_files = []
        if os.path.exists(OFFICIAL_WALLPAPERS_DIR):
            for ext in ("*.png", "*.jpeg", "*.jpg", "*.webp"):
                wallpaper_files.extend(glob.glob(os.path.join(OFFICIAL_WALLPAPERS_DIR, ext)))

        # Sort so CelWeave wallpapers are on top
        wallpaper_files = sorted(wallpaper_files, key=lambda p: (0 if "CelWeave" in p else 1, os.path.basename(p)))

        selected_idx = 0
        for i, path in enumerate(wallpaper_files):
            name = os.path.splitext(os.path.basename(path))[0]
            self._wp_combo.addItem(name, path)
            if os.path.abspath(path) == os.path.abspath(current_wp):
                selected_idx = i

        # If custom path not in list
        if current_wp and not any(os.path.abspath(p) == os.path.abspath(current_wp) for p in wallpaper_files):
            self._wp_combo.addItem(f"Custom: {os.path.basename(current_wp)}", current_wp)
            selected_idx = self._wp_combo.count() - 1

        self._wp_combo.setCurrentIndex(selected_idx)

    def _on_wallpaper_selected(self, index: int) -> None:
        if index >= 0:
            path = self._wp_combo.itemData(index)
            if path and os.path.exists(path):
                self._config["wallpaper_path"] = path
                if self._on_theme_changed:
                    self._on_theme_changed()

    def _browse_wallpaper(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Wallpaper",
            OFFICIAL_WALLPAPERS_DIR if os.path.exists(OFFICIAL_WALLPAPERS_DIR) else "",
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            self._config["wallpaper_path"] = path
            self._populate_wallpapers()
            if self._on_theme_changed:
                self._on_theme_changed()

    def _on_glass_changed(self, value: int) -> None:
        opacity = round(value / 100.0, 2)
        self._glass_lbl.setText(f"Liquid Glass Opacity: {value}%")
        self._config["glass_opacity"] = opacity
        if self._on_theme_changed:
            self._on_theme_changed()

    def _on_tint_changed(self, value: int) -> None:
        opacity = round(value / 100.0, 2)
        self._tint_lbl.setText(f"Wallpaper Dark Tint: {value}%")
        self._config["wallpaper_tint_opacity"] = opacity
        if self._on_theme_changed:
            self._on_theme_changed()

    def _save_port(self, key: str, value: int) -> None:
        self._config[key] = value
        log.debug("Setting %s = %d", key, value)

    def _browse_binary(self, line_edit: QLineEdit, config_key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {config_key} binary", "",
        )
        if path:
            line_edit.setText(path)
            self._config[config_key] = path

    def _browse_ss_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Screenshot Directory", "",
        )
        if path:
            self._ss_dir_input.setText(path)
            self._config["screenshot_dir"] = path

    def _reset_all(self) -> None:
        self._config.reset()
        for key, spin in self._port_widgets.items():
            spin.setValue(self._config.get(key, 5555))
        self._scrcpy_input.setText(self._config.get("scrcpy_bin", "scrcpy"))
        self._adb_input.setText(self._config.get("adb_bin", "adb"))
        self._ss_dir_input.setText("")
        
        # Reset Theme
        self._populate_wallpapers()
        self._glass_slider.setValue(65)
        self._tint_slider.setValue(70)
        if self._on_theme_changed:
            self._on_theme_changed()
        log.info("Settings reset to defaults")
