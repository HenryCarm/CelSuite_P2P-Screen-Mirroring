"""
Mirror Phone tab — the primary interface for ScrcpyUltimateLink.

Handles device discovery, connection, scrcpy launch, remote control,
hardware dashboard, clipboard sync, and screen capture.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import timedelta

from PySide6.QtCore import QTimer, Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig
from src.constants import (
    APP_NAME,
    APP_VERSION,
    DASHBOARD_REFRESH_SEC,
    DEFAULT_ADB_PORT,
    ConnectionState,
    KEYCODE_BACK,
    KEYCODE_HOME,
    KEYCODE_POWER,
    KEYCODE_RECENTS,
    KEYCODE_SCREEN_OFF,
    KEYCODE_VOLUME_DOWN,
    KEYCODE_VOLUME_UP,
    SCRCPY_PRESETS,
)
from src.logger import get_logger
from src.networking import adb, heartbeat, latency, scanner
from src.ui.animations import AnimatedButton
from src.ui.widgets.collapsible_card import CollapsibleCard
from src.ui.widgets.dashboard import DashboardWidget
from src.ui.widgets.heartbeat_indicator import HeartbeatIndicator
from src.ui.widgets.log_panel import LogPanel
from src.ui.widgets.section_card import SectionCard

log = get_logger(__name__)


class MirrorTab(QWidget):
    """Main mirror phone tab with connection, controls, and dashboard."""

    connection_state_changed = Signal(str)
    _sig_telemetry_ready = Signal(dict, object)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._phone_ip: str | None = None
        self._adb_port: int = config.get("adb_port", DEFAULT_ADB_PORT)
        self._connected = False
        self._connect_time: float | None = None
        self._dashboard_timer: QTimer | None = None
        self._duration_timer: QTimer | None = None

        # Initialize networking components
        self._heartbeat = heartbeat.HeartbeatListener(config)
        self._broadcaster = heartbeat.DiscoveryBroadcaster(config)
        self._scanner = scanner.SubnetScanner(config)

        self._heartbeat_indicator = HeartbeatIndicator(size=0)
        self._status_label = QLabel()

        # Build UI
        self._build_ui()

        # Connect signals
        self._sig_telemetry_ready.connect(self._on_telemetry_ready)
        self._heartbeat.heartbeat_received.connect(self._on_heartbeat)
        self._heartbeat.state_changed.connect(self._on_state_changed)
        self._heartbeat.clipboard_received.connect(self._on_clipboard_received)
        self._scanner.device_found.connect(self._on_device_found)
        self._scanner.scan_complete.connect(self._on_scan_complete)

    def _build_ui(self) -> None:
        """Construct the tab layout with clean, un-cluttered visual hierarchy."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # ── 1. HERO CONNECTION CARD (Main Central Focus) ─────────────
        hero_card = QFrame()
        hero_card.setObjectName("hero-card")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setSpacing(16)

        # Header Title inside Hero Card
        hero_header = QHBoxLayout()
        hero_title = QLabel("📱 Connect & Mirror Phone")
        hero_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #F0F0F5;")
        
        local_ip = heartbeat.get_local_ip()
        self._current_local_ip = local_ip
        
        ip_box = QHBoxLayout()
        ip_box.setSpacing(6)
        
        self._ip_label = QLabel(f"📡 PC IP: {local_ip}")
        self._ip_label.setObjectName("subtitle")
        
        self._btn_copy_ip = QPushButton("📋 Copy")
        self._btn_copy_ip.setToolTip("Copy PC IP address to clipboard")
        self._btn_copy_ip.setStyleSheet("""
            QPushButton {
                background-color: #2D2D3D;
                color: #A0A0B0;
                border: 1px solid #3E3E50;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3E3E50;
                color: #FFFFFF;
                border-color: #7C4DFF;
            }
        """)
        self._btn_copy_ip.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copy_ip.clicked.connect(self._copy_ip_to_clipboard)
        
        ip_box.addWidget(self._ip_label)
        ip_box.addWidget(self._btn_copy_ip)

        hero_header.addWidget(hero_title)
        hero_header.addStretch()
        hero_header.addLayout(ip_box)
        hero_layout.addLayout(hero_header)

        # Primary One-Tap Connect Button
        self._hero_connect_btn = QPushButton("⚡ One-Tap Connect")
        self._hero_connect_btn.setObjectName("hero-button")
        self._hero_connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hero_connect_btn.clicked.connect(self._start_auto_discover)
        hero_layout.addWidget(self._hero_connect_btn)

        # Quick action row (Discovered / Saved / Scan / Disconnect)
        conn_actions_layout = QHBoxLayout()
        self._auto_btn = AnimatedButton("📡 Auto-Discover")
        self._auto_btn.clicked.connect(self._start_auto_discover)

        self._saved_btn = AnimatedButton("💾 Saved IP")
        self._saved_btn.clicked.connect(self._connect_saved_ip)

        self._scan_btn = AnimatedButton("🔍 Subnet Scan")
        self._scan_btn.clicked.connect(self._start_subnet_scan)

        self._disconnect_btn = AnimatedButton("❌ Disconnect")
        self._disconnect_btn.setObjectName("action-danger")
        self._disconnect_btn.clicked.connect(self._disconnect)
        self._disconnect_btn.setEnabled(False)

        conn_actions_layout.addWidget(self._auto_btn)
        conn_actions_layout.addWidget(self._saved_btn)
        conn_actions_layout.addWidget(self._scan_btn)
        conn_actions_layout.addWidget(self._disconnect_btn)
        hero_layout.addLayout(conn_actions_layout)

        # Advanced connection options (Video quality preset)
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Video Quality Preset:"))
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(SCRCPY_PRESETS.keys())
        saved_preset = self._config.get("scrcpy_preset", "Balanced (Default)")
        idx = self._preset_combo.findText(saved_preset)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self._preset_combo)
        preset_layout.addStretch()

        self._duration_label = QLabel("")
        self._duration_label.setObjectName("subtitle")
        preset_layout.addWidget(self._duration_label)

        hero_layout.addLayout(preset_layout)

        main_layout.addWidget(hero_card)

        # ── 2. COLLAPSIBLE REMOTE CONTROLS ────────────────────────────
        remote_card = CollapsibleCard("🎮 Quick Remote Controls (Back, Home, Volume, Power)", expanded=False)
        ctrl_main = QVBoxLayout()

        # Nav row
        nav_layout = QHBoxLayout()
        for label, keycode in [
            ("⬅ Back", KEYCODE_BACK),
            ("⌂ Home", KEYCODE_HOME),
            ("◻ Recents", KEYCODE_RECENTS),
        ]:
            btn = AnimatedButton(label)
            btn.clicked.connect(lambda _, k=keycode: self._send_key(k))
            nav_layout.addWidget(btn)
        ctrl_main.addLayout(nav_layout)

        # Media + power row
        media_layout = QHBoxLayout()
        for label, keycode in [
            ("🔊 Vol+", KEYCODE_VOLUME_UP),
            ("🔉 Vol−", KEYCODE_VOLUME_DOWN),
            ("⏻ Power", KEYCODE_POWER),
            ("📴 Screen Off", KEYCODE_SCREEN_OFF),
        ]:
            btn = AnimatedButton(label)
            btn.clicked.connect(lambda _, k=keycode: self._send_key(k))
            media_layout.addWidget(btn)
        ctrl_main.addLayout(media_layout)

        # Custom keycode row
        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("Custom Keycode:"))
        self._custom_key_input = QSpinBox()
        self._custom_key_input.setRange(0, 999)
        custom_key_btn = AnimatedButton("Send Key")
        custom_key_btn.clicked.connect(self._send_custom_key)
        custom_layout.addWidget(self._custom_key_input)
        custom_layout.addWidget(custom_key_btn)
        custom_layout.addStretch()
        ctrl_main.addLayout(custom_layout)

        remote_card.addLayout(ctrl_main)
        main_layout.addWidget(remote_card)

        # ── 3. COLLAPSIBLE TOOLS (Clipboard & Screen Capture & URL) ─────
        tools_card = CollapsibleCard("🧰 Quick Tools (Clipboard, Capture & URL)", expanded=False)
        tools_main = QVBoxLayout()

        # Row 1: Clipboard & Screenshot
        row1 = QHBoxLayout()
        self._auto_clip_cb = QCheckBox("Auto Clipboard Sync")
        self._auto_clip_cb.setChecked(self._config.get("auto_clip_sync", False))
        self._auto_clip_cb.toggled.connect(
            lambda v: self._config.__setitem__("auto_clip_sync", v)
        )
        push_clip_btn = AnimatedButton("⬆ Push Clipboard")
        push_clip_btn.clicked.connect(self._push_clipboard)

        pull_clip_btn = AnimatedButton("⬇ Pull Clipboard")
        pull_clip_btn.clicked.connect(self._pull_clipboard)

        screenshot_btn = AnimatedButton("📸 Take Screenshot")
        screenshot_btn.clicked.connect(self._take_screenshot)

        row1.addWidget(self._auto_clip_cb)
        row1.addWidget(push_clip_btn)
        row1.addWidget(pull_clip_btn)
        row1.addWidget(screenshot_btn)
        tools_main.addLayout(row1)

        # Row 2: Open URL
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Open URL:"))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://example.com")
        url_btn = AnimatedButton("Open on Phone")
        url_btn.clicked.connect(self._open_url)
        row2.addWidget(self._url_input)
        row2.addWidget(url_btn)
        tools_main.addLayout(row2)

        tools_card.addLayout(tools_main)
        main_layout.addWidget(tools_card)

        # ── 4. COLLAPSIBLE HARDWARE TELEMETRY ─────────────────────────
        self._telemetry_card = CollapsibleCard("📊 Live Hardware Telemetry (CPU, RAM, Latency)", expanded=False)
        self._dashboard = DashboardWidget()
        self._dashboard.refresh_btn.clicked.connect(self._refresh_dashboard)
        self._telemetry_card._toggle_button.clicked.connect(self._on_telemetry_toggled)
        self._telemetry_card.addWidget(self._dashboard)
        main_layout.addWidget(self._telemetry_card)

        # Log panel at bottom
        self._log_panel = LogPanel()
        main_layout.addWidget(self._log_panel)

        main_layout.addStretch()
        scroll.setWidget(container)

        # Set central layout for this widget tab
        tab_layout = QVBoxLayout(self)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    # ── Connection Handlers ───────────────────────────────────────────────

    def _start_auto_discover(self) -> None:
        """Refresh local IP and start heartbeat listener + discovery broadcaster + subnet probe."""
        local_ip = heartbeat.get_local_ip()
        self._current_local_ip = local_ip
        self._ip_label.setText(f"📡 PC IP: {local_ip}")

        self._update_status("Discovering...", "status-warning")
        self._heartbeat_indicator.set_state("discovering")
        self._heartbeat.start()
        self._broadcaster.start()
        self._scanner.start_scan()
        log.info("Auto-discovery started (PC IP: %s)", local_ip)

    def _connect_saved_ip(self) -> None:
        """Try connecting to the last known phone IP."""
        saved_ip = self._config.get("last_phone_ip", "")
        if not saved_ip:
            log.warning("No saved phone IP found")
            self._update_status("\U0001f534  No saved IP", "status-error")
            return
        self._update_status(f"Connecting to {saved_ip}...", "status-warning")
        self._heartbeat_indicator.set_state("connecting")
        port = self._config.get("last_phone_port", DEFAULT_ADB_PORT)
        threading.Thread(
            target=self._connect_worker, args=(saved_ip, port),
            daemon=True,
        ).start()

    def _start_subnet_scan(self) -> None:
        """Launch a subnet scan."""
        self._update_status("Scanning subnet...", "status-warning")
        self._heartbeat_indicator.set_state("discovering")
        self._scan_btn.setEnabled(False)
        self._scanner.start_scan()

    def _disconnect(self) -> None:
        """Disconnect from the phone."""
        self._scanner.cancel()
        self._heartbeat.stop()
        self._broadcaster.stop()
        adb.stop_scrcpy()
        if self._phone_ip:
            adb.disconnect(self._config, self._phone_ip, getattr(self, "_adb_port", DEFAULT_ADB_PORT))
        else:
            adb.disconnect_all(self._config)
        self._set_disconnected()
        log.info("Disconnected from phone")

    # ── Signal Handlers ───────────────────────────────────────────────────

    def _on_heartbeat(self, ip: str, port: int) -> None:
        """Handle incoming heartbeat — connect and launch."""
        if self._connected and self._phone_ip == ip:
            # Already actively connected and mirroring; heartbeat is just a keep-alive
            return
        self._connect_worker(ip, port)

    def _on_clipboard_received(self, text: str) -> None:
        try:
            QApplication.clipboard().setText(text)
            log.info("📋 Clipboard synced from phone (Quick Settings): %s", text[:50])
        except Exception as e:
            log.error("Failed to set clipboard: %s", e)

    def _on_state_changed(self, state: str) -> None:
        """Handle connection state changes from heartbeat listener."""
        self.connection_state_changed.emit(state)

    def _on_device_found(self, ip: str) -> None:
        """Handle subnet scan finding a device."""
        threading.Thread(
            target=self._connect_worker,
            args=(ip, self._config.get("adb_port", DEFAULT_ADB_PORT)),
            daemon=True,
        ).start()

    def _on_scan_complete(self, result: str | None) -> None:
        """Handle subnet scan completion."""
        self._scan_btn.setEnabled(True)
        if result is None and not self._connected:
            self._update_status("No devices found on subnet", "status-error")
            self._heartbeat_indicator.set_state("error")

    # ── Workers ───────────────────────────────────────────────────────────

    def _connect_worker(self, ip: str, port: int) -> None:
        """Connect to phone and launch scrcpy (runs in background thread)."""
        preset_name = self._preset_combo.currentText()
        extra_args = SCRCPY_PRESETS.get(preset_name, [])

        success, msg = adb.launch_scrcpy(self._config, ip, port, extra_args)

        if success:
            QTimer.singleShot(0, lambda: self._set_connected(ip, port))
        else:
            QTimer.singleShot(
                0, lambda: self._update_status(f"{msg}", "status-error")
            )
            QTimer.singleShot(
                0, lambda: self._heartbeat_indicator.set_state("error")
            )

    # ── UI State ──────────────────────────────────────────────────────────

    def _set_connected(self, ip: str, port: int = DEFAULT_ADB_PORT) -> None:
        """Update UI to connected state and emit signal."""
        self._phone_ip = ip
        self._adb_port = port
        self._connected = True
        self._connect_time = time.time()
        
        self._disconnect_btn.setEnabled(True)
        self._auto_btn.setEnabled(False)
        self._saved_btn.setEnabled(False)
        self._scan_btn.setEnabled(False)
        
        # Stop broadcaster when connected to save battery and network bandwidth
        self._broadcaster.stop()
        
        self._start_dashboard_timer()
        self._start_duration_timer()
        self.connection_state_changed.emit(ConnectionState.MIRRORING)

    def _set_disconnected(self) -> None:
        """Update UI to disconnected state."""
        self._phone_ip = None
        self._connected = False
        self._connect_time = None
        
        self._duration_label.setText("")
        self._disconnect_btn.setEnabled(False)
        self._auto_btn.setEnabled(True)
        self._saved_btn.setEnabled(True)
        self._scan_btn.setEnabled(True)
        self._dashboard.reset()
        self._stop_dashboard_timer()
        self._stop_duration_timer()
        self.connection_state_changed.emit(ConnectionState.DISCONNECTED)

    def _update_status(self, text: str, obj_name: str = "status") -> None:
        # Legacy method; status is now handled by MainWindow
        pass

    # ── Dashboard & Battery Optimizations ─────────────────────────────────

    def _on_telemetry_toggled(self) -> None:
        """Fetch metrics immediately when user expands the telemetry card."""
        if hasattr(self, "_telemetry_card") and self._telemetry_card._is_expanded:
            self._refresh_dashboard()

    def _start_dashboard_timer(self) -> None:
        """Gentle 60s dashboard timer to conserve phone and PC battery."""
        if self._dashboard_timer is None:
            self._dashboard_timer = QTimer()
            self._dashboard_timer.timeout.connect(self._on_dashboard_timer_tick)
        self._dashboard_timer.start(60000)  # 60s instead of aggressive 5s
        self._refresh_dashboard()  # immediate first refresh

    def _on_dashboard_timer_tick(self) -> None:
        """Only query hardware over ADB if the telemetry card is actively open."""
        if self._connected and hasattr(self, "_telemetry_card") and self._telemetry_card._is_expanded:
            self._refresh_dashboard()

    def _stop_dashboard_timer(self) -> None:
        if self._dashboard_timer:
            self._dashboard_timer.stop()

    def _on_telemetry_ready(self, info: dict, lat: object) -> None:
        """Update dashboard widgets on main GUI thread via queued signal."""
        self._dashboard.update_info(info)
        self._dashboard.update_latency(lat)

    def _refresh_dashboard(self) -> None:
        """Refresh hardware info with logging."""
        phone_ip = self._phone_ip
        adb_port = getattr(self, "_adb_port", DEFAULT_ADB_PORT)
        if not phone_ip:
            phone_ip, port = adb.get_connected_phone(self._config)
            if phone_ip:
                self._phone_ip = phone_ip
                if port:
                    self._adb_port = port
                    adb_port = port
        if not phone_ip:
            log.info("[Hardware Dashboard] Not connected — refresh skipped.")
            return

        log.info("[Hardware Dashboard] Querying device metrics for %s:%s...", phone_ip, adb_port)

        def worker() -> None:
            info = adb.get_hardware_info(
                self._config, phone_ip, adb_port
            )
            lat, _ = latency.measure_latency(phone_ip, adb_port)
            self._sig_telemetry_ready.emit(info, lat)

        threading.Thread(target=worker, daemon=True).start()

    # ── Duration Timer ────────────────────────────────────────────────────

    def _start_duration_timer(self) -> None:
        if self._duration_timer is None:
            self._duration_timer = QTimer()
            self._duration_timer.timeout.connect(self._update_duration)
        self._duration_timer.start(1000)

    def _stop_duration_timer(self) -> None:
        if self._duration_timer:
            self._duration_timer.stop()

    def _update_duration(self) -> None:
        if self._connect_time:
            elapsed = int(time.time() - self._connect_time)
            td = str(timedelta(seconds=elapsed))
            self._duration_label.setText(f"\u23f1  Connected for {td}")

    # ── Remote Control ────────────────────────────────────────────────────

    def _send_key(self, keycode: int) -> None:
        if not self._phone_ip:
            return
        threading.Thread(
            target=lambda: adb.send_keyevent(
                self._config, keycode, self._phone_ip, self._adb_port,
            ),
            daemon=True,
        ).start()

    def _send_custom_key(self) -> None:
        code = self._custom_key_input.value()
        self._send_key(code)

    # ── Clipboard ─────────────────────────────────────────────────────────

    def _push_clipboard(self) -> None:
        if not self._phone_ip:
            return
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            text = clipboard.text()
            if text:
                threading.Thread(
                    target=lambda: adb.send_broadcast(
                        self._config,
                        "HenryJayZ.CelSuite.ScrcpyHeartbeat.SET_CLIPBOARD",
                        {"text": text},
                        self._phone_ip, self._adb_port,
                    ),
                    daemon=True,
                ).start()

    def _pull_clipboard(self) -> None:
        if not self._phone_ip:
            return
        threading.Thread(
            target=lambda: adb.send_broadcast(
                self._config,
                "HenryJayZ.CelSuite.ScrcpyHeartbeat.GET_CLIPBOARD",
                phone_ip=self._phone_ip, adb_port=self._adb_port,
            ),
            daemon=True,
        ).start()

    # ── Screen Capture ────────────────────────────────────────────────────

    def _take_screenshot(self) -> None:
        if not self._phone_ip:
            return
        save_dir = self._config.screenshot_directory()
        filename = f"screenshot_{int(time.time())}.png"
        save_path = os.path.join(save_dir, filename)

        def worker() -> None:
            ok, msg = adb.take_screenshot(
                self._config, save_path, self._phone_ip, self._adb_port,
            )
            if ok:
                log.info("Screenshot: %s", save_path)
            else:
                log.error("Screenshot failed: %s", msg)

        threading.Thread(target=worker, daemon=True).start()

    # ── Open URL ──────────────────────────────────────────────────────────

    def _open_url(self) -> None:
        url = self._url_input.text().strip()
        if not url or not self._phone_ip:
            return
        threading.Thread(
            target=lambda: adb.open_url(
                self._config, url, self._phone_ip, self._adb_port,
            ),
            daemon=True,
        ).start()

    # ── Copy IP Helper ───────────────────────────────────────────────────

    def _copy_ip_to_clipboard(self) -> None:
        ip = getattr(self, "_current_local_ip", heartbeat.get_local_ip())
        QApplication.clipboard().setText(ip)
        self._btn_copy_ip.setText("✅ Copied!")
        self._btn_copy_ip.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: #FFFFFF;
                border: 1px solid #10B981;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        QTimer.singleShot(2000, lambda: self._btn_copy_ip.setText("📋 Copy"))
        QTimer.singleShot(2000, lambda: self._btn_copy_ip.setStyleSheet("""
            QPushButton {
                background-color: #2D2D3D;
                color: #A0A0B0;
                border: 1px solid #3E3E50;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3E3E50;
                color: #FFFFFF;
                border-color: #7C4DFF;
            }
        """))

    # ── Preset ────────────────────────────────────────────────────────────

    def _on_preset_changed(self, text: str) -> None:
        self._config["scrcpy_preset"] = text

    # ── Cleanup ───────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Stop all background services."""
        self._heartbeat.stop()
        self._broadcaster.stop()
        self._scanner.cancel()
        self._stop_dashboard_timer()
        self._stop_duration_timer()

    @property
    def phone_ip(self) -> str | None:
        return self._phone_ip

    @property
    def is_connected(self) -> bool:
        return self._connected
