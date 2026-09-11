"""
Main application window for CelStudio Scrcpy Heartbeat.

Assembles all tabs, sidebar navigation, CelStudio Wallpaper Engine,
and status monitoring with heartbeat indicator.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig
from src.constants import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_ICON,
    DEFAULT_WALLPAPER,
    ConnectionState,
)
from src.logger import get_logger
from src.networking import adb
from src.transfer.tcp_server import TCPFileServer
from src.ui.about_tab import AboutTab
from src.ui.logs_tab import LogsTab
from src.ui.mirror_tab import MirrorTab
from src.ui.settings_tab import SettingsTab
from src.ui.styles import build_stylesheet
from src.ui.transfer_tab import TransferTab
from src.ui.widgets.heartbeat_indicator import HeartbeatIndicator

log = get_logger(__name__)


class CelWallpaperWidget(QWidget):
    """Background canvas supporting dynamic CelStudio wallpapers & tint overlay."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setObjectName("central-wallpaper-widget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cached_pixmap: QPixmap | None = None
        self._cached_path: str = ""
        self._cached_scaled: QPixmap | None = None
        self._cached_size: QSize = QSize()

    def _get_pixmap(self) -> QPixmap | None:
        path = self._config.get("wallpaper_path", DEFAULT_WALLPAPER)
        if path != self._cached_path or self._cached_pixmap is None:
            self._cached_path = path
            self._cached_scaled = None
            if os.path.exists(path):
                self._cached_pixmap = QPixmap(path)
            else:
                self._cached_pixmap = None
        return self._cached_pixmap

    def paintEvent(self, event) -> None:
        painter = QPainter(self)

        # 1. Base dark background
        painter.fillRect(self.rect(), QColor("#08120B"))

        # 2. Render Cached Scaled Wallpaper (Optimized to save GPU/CPU cycles)
        pix = self._get_pixmap()
        if pix and not pix.isNull():
            if self._cached_scaled is None or self._cached_size != self.size():
                self._cached_size = self.size()
                self._cached_scaled = pix.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            if self._cached_scaled:
                x = (self.width() - self._cached_scaled.width()) // 2
                y = (self.height() - self._cached_scaled.height()) // 2
                painter.drawPixmap(x, y, self._cached_scaled)

        # 3. Dark Overlay Tint to protect text contrast
        tint_opacity = float(self._config.get("wallpaper_tint_opacity", 0.70))
        tint_alpha = int(max(0.0, min(1.0, tint_opacity)) * 255)
        painter.fillRect(self.rect(), QColor(6, 16, 10, tint_alpha))
        painter.fillRect(self.rect(), QColor(10, 8, 18, tint_alpha))


class MainWindow(QMainWindow):
    """The main CelStudio application window with tabbed interface."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._build_window()
        self._build_menubar()
        self._build_tabs()
        self._start_services()

    def _build_window(self) -> None:
        """Configure window properties."""
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(QSize(850, 620))

        # Set Window Icon
        icon_path = self._config.get("app_icon", DEFAULT_ICON)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        elif os.path.exists("icon.png"):
            self.setWindowIcon(QIcon("icon.png"))

        # Restore saved window geometry
        w = self._config.get("window_width", 980)
        h = self._config.get("window_height", 740)
        x = self._config.get("window_x", -1)
        y = self._config.get("window_y", -1)
        self.resize(w, h)
        if x >= 0 and y >= 0:
            self.move(x, y)

        # Apply CelStudio Liquid Glass stylesheet
        self.apply_theme()

    def apply_theme(self) -> None:
        """Dynamically generate and apply the liquid glass stylesheet."""
        opacity = float(self._config.get("glass_opacity", 0.65))
        stylesheet = build_stylesheet(opacity)
        self.setStyleSheet(stylesheet)
        if hasattr(self, "_wallpaper_widget"):
            self._wallpaper_widget.update()

    def _build_menubar(self) -> None:
        """Build the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        quit_action = QAction("Exit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_tabs(self) -> None:
        """Build the sidebar navigation and content stack with Wallpaper Engine."""
        self._wallpaper_widget = CelWallpaperWidget(self._config, self)
        self.setCentralWidget(self._wallpaper_widget)

        # Main Layout: Sidebar on left, Stack on right
        layout = QHBoxLayout(self._wallpaper_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar Container with Liquid Glass
        sidebar_container = QWidget()
        sidebar_container.setObjectName("sidebar-container")
        sidebar_container.setFixedWidth(245)
        
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(10, 18, 10, 18)
        sidebar_layout.setSpacing(8)

        # App Title in Sidebar
        title_box = QHBoxLayout()
        title_box.setContentsMargins(6, 0, 6, 4)
        title_box.setSpacing(8)
        
        logo_icon = QLabel()
        logo_icon.setFixedSize(24, 24)
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "icon.png")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            if not pix.isNull():
                logo_icon.setPixmap(pix.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                logo_icon.setText("✨")
        else:
            logo_icon.setText("✨")
        title_box.addWidget(logo_icon)

        title_lbl = QLabel(APP_NAME)
        title_lbl.setStyleSheet("color: #F0FDF4; font-size: 12px; font-weight: bold; letter-spacing: 0.2px;")
        title_box.addWidget(title_lbl)
        title_box.addStretch()
        sidebar_layout.addLayout(title_box)

        # Sidebar List
        self._sidebar = QListWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.currentRowChanged.connect(self._on_sidebar_changed)
        sidebar_layout.addWidget(self._sidebar)

        sidebar_layout.addStretch()

        # Connection Status in Sidebar
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(12, 6, 12, 6)
        self._heartbeat = HeartbeatIndicator(size=22)
        self._heartbeat.set_state("disconnected")
        status_layout.addWidget(self._heartbeat)

        self._conn_label = QLabel("Disconnected")
        self._conn_label.setStyleSheet("color: #9CA3AF; font-size: 12px; font-weight: bold;")
        status_layout.addWidget(self._conn_label)
        status_layout.addStretch()
        sidebar_layout.addLayout(status_layout)

        layout.addWidget(sidebar_container)

        # Content Stack with Glassmorphic Panes
        self._stack = QStackedWidget()
        self._stack.setObjectName("content-stack")
        layout.addWidget(self._stack)

        self._mirror_tab = MirrorTab(self._config)
        self._mirror_tab.connection_state_changed.connect(self._on_connection_state)

        self._transfer_tab = TransferTab(
            self._config,
            get_phone_ip=lambda: self._mirror_tab.phone_ip,
        )

        self._logs_tab = LogsTab(self._config)
        self._settings_tab = SettingsTab(self._config, on_theme_changed=self.apply_theme)
        self._about_tab = AboutTab(self._config)

        # Register navigation tabs
        tabs = [
            ("📱  Mirror Phone", self._mirror_tab),
            ("📤  File Transfer", self._transfer_tab),
            ("📜  Logs", self._logs_tab),
            ("🎨  Settings", self._settings_tab),
            ("❓  About", self._about_tab),
        ]

        for name, widget in tabs:
            self._sidebar.addItem(name)
            self._stack.addWidget(widget)

        self._sidebar.setCurrentRow(0)

    def _on_sidebar_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def _start_services(self) -> None:
        """Start background network services."""
        self._file_server = TCPFileServer(
            port=self._config.get("tcp_transfer_port", 5558),
            save_dir=self._config.screenshot_directory(),
        )
        self._file_server.file_received.connect(self._on_file_received)
        self._file_server.start()
        log.info("Application started — TCP file server active")

    def _on_file_received(self, filename: str, filepath: str) -> None:
        """Handle incoming file from phone."""
        if filename == "clipboard.txt":
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                QApplication.clipboard().setText(content)
                log.info("📋 Clipboard synced from phone: %s", content[:50])
            except Exception as e:
                log.error("Failed to read received clipboard: %s", e)

    # ── Signal Handlers ───────────────────────────────────────────────────

    def _on_connection_state(self, state: str) -> None:
        """Update status bar heartbeat indicator and label."""
        self._heartbeat.set_state(state)

        labels = {
            ConnectionState.DISCONNECTED: ("Disconnected", "#9CA3AF"),
            ConnectionState.DISCOVERING: ("Discovering...", "#F59E0B"),
            ConnectionState.CONNECTING: ("Connecting...", "#F59E0B"),
            ConnectionState.CONNECTED: ("Connected", "#10B981"),
            ConnectionState.MIRRORING: ("Mirroring Active", "#10B981"),
            ConnectionState.ERROR: ("Connection Error", "#EF4444"),
        }
        label_text, color = labels.get(state, (state, "#9CA3AF"))
        self._conn_label.setText(label_text)
        self._conn_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")

    # ── Dialogs ───────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        """Switch to the About tab."""
        for i in range(self._stack.count()):
            if isinstance(self._stack.widget(i), AboutTab):
                self._sidebar.setCurrentRow(i)
                break

    # ── Window Events ─────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        """Dynamically save window size whenever resized."""
        super().resizeEvent(event)
        if not self.isMaximized() and not self.isMinimized():
            self._config["window_width"] = self.width()
            self._config["window_height"] = self.height()

    def moveEvent(self, event) -> None:
        """Dynamically save window position whenever moved."""
        super().moveEvent(event)
        if not self.isMaximized() and not self.isMinimized():
            self._config["window_x"] = self.x()
            self._config["window_y"] = self.y()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close — confirm if connected, save geometry."""
        if self._mirror_tab.is_connected:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A device is still connected. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        # Save window geometry
        self._config.update({
            "window_width": self.width(),
            "window_height": self.height(),
            "window_x": self.x(),
            "window_y": self.y(),
        })

        # Cleanup
        self._mirror_tab.cleanup()
        self._file_server.stop()
        adb.stop_scrcpy()
        adb.disconnect_all(self._config)
        log.info("Application closed")

        event.accept()

    def keyPressEvent(self, event) -> None:
        """Handle global keyboard shortcuts."""
        if event.key() == Qt.Key.Key_F5:
            self._mirror_tab._refresh_dashboard()
        else:
            super().keyPressEvent(event)
