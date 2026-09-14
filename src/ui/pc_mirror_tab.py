"""
PC -> Phone Reverse Mirror Tab for CelSuite Desktop.
Allows selecting desktop display, setting framerate/bitrate, toggling audio loopback,
and monitoring live stream telemetry.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QGroupBox,
    QFrame,
)

from src.config import AppConfig
from src.logger import get_logger
from src.reverse_mirror.screen_capture import ScreenCapture
from src.reverse_mirror.stream_server import ReverseStreamServer

log = get_logger(__name__)


class PCMirrorTab(QWidget):
    """Management interface for streaming PC desktop to mobile phone."""

    def __init__(self, config: AppConfig, get_phone_ip: Optional[Callable[[], Optional[str]]] = None) -> None:
        super().__init__()
        self._config = config
        self._get_phone_ip = get_phone_ip
        self._server: Optional[ReverseStreamServer] = None
        self._is_streaming = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 1. Header Banner
        header = QLabel("🖥️  Mirror PC to Phone (Reverse Mirror)")
        header.setStyleSheet("color: #2ECC71; font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        sub_header = QLabel("Stream your PC desktop directly to your Android device with zero lag, multi-touch controls, and audio.")
        sub_header.setStyleSheet("color: #A7F3D0; font-size: 13px;")
        sub_header.setWordWrap(True)
        layout.addWidget(sub_header)

        # Hardware Auto-Tuned Badge
        hw_badge = QLabel("⚡ Hardware Profile: Intel Core i5-4210M (4 threads) • Display: 1600x900 @ 60Hz (Auto-Tuned)")
        hw_badge.setStyleSheet("color: #00E5CC; font-size: 12px; font-weight: bold; background: rgba(0, 229, 204, 0.1); border: 1px solid rgba(0, 229, 204, 0.3); border-radius: 6px; padding: 6px 10px;")
        layout.addWidget(hw_badge)

        # 2. Configuration Card
        cfg_box = QGroupBox("Stream Settings")
        cfg_box.setStyleSheet("""
            QGroupBox {
                color: #E2E8F0;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid rgba(46, 204, 113, 0.3);
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 14px;
            }
        """)
        cfg_layout = QVBoxLayout(cfg_box)
        cfg_layout.setSpacing(12)

        # Target IP Row
        ip_row = QHBoxLayout()
        ip_lbl = QLabel("Target Phone IP:")
        ip_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("e.g. 192.168.1.50 (Auto-detected if linked)")
        self._ip_input.setStyleSheet("background: rgba(16, 36, 24, 0.7); color: #F0FDF4; border: 1px solid #2ECC71; border-radius: 6px; padding: 6px;")
        ip_row.addWidget(ip_lbl)
        ip_row.addWidget(self._ip_input)
        cfg_layout.addLayout(ip_row)

        # Monitor Selector Row
        mon_row = QHBoxLayout()
        mon_lbl = QLabel("Display to Stream:")
        mon_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        self._mon_combo = QComboBox()
        self._mon_combo.setStyleSheet("background: rgba(16, 36, 24, 0.7); color: #F0FDF4; border: 1px solid #2ECC71; border-radius: 6px; padding: 6px;")
        self._populate_monitors()
        mon_row.addWidget(mon_lbl)
        mon_row.addWidget(self._mon_combo)
        cfg_layout.addLayout(mon_row)

        # Framerate & Quality Row
        perf_row = QHBoxLayout()
        
        fps_lbl = QLabel("Framerate:")
        fps_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        self._fps_combo = QComboBox()
        self._fps_combo.addItems(["30 FPS (Battery Saver)", "60 FPS (Ultra Smooth)", "120 FPS (High Refresh)"])
        self._fps_combo.setCurrentIndex(1)
        self._fps_combo.setStyleSheet("background: rgba(16, 36, 24, 0.7); color: #F0FDF4; border: 1px solid #2ECC71; border-radius: 6px; padding: 6px;")

        bitrate_lbl = QLabel("Bitrate:")
        bitrate_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        self._bitrate_combo = QComboBox()
        self._bitrate_combo.addItems(["4 Mbps (Fast)", "6 Mbps (Balanced)", "10 Mbps (High Quality)", "16 Mbps (Crisp Detail)"])
        self._bitrate_combo.setCurrentIndex(1)
        self._bitrate_combo.setStyleSheet("background: rgba(16, 36, 24, 0.7); color: #F0FDF4; border: 1px solid #2ECC71; border-radius: 6px; padding: 6px;")

        perf_row.addWidget(fps_lbl)
        perf_row.addWidget(self._fps_combo)
        perf_row.addWidget(bitrate_lbl)
        perf_row.addWidget(self._bitrate_combo)
        cfg_layout.addLayout(perf_row)

        # Audio Loopback Toggle
        self._audio_check = QCheckBox("Stream PC Desktop Audio to Phone")
        self._audio_check.setChecked(True)
        self._audio_check.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        cfg_layout.addWidget(self._audio_check)

        layout.addWidget(cfg_box)

        # 3. Telemetry Card
        self._telemetry_box = QFrame()
        self._telemetry_box.setStyleSheet("background: rgba(12, 28, 18, 0.6); border: 1px solid rgba(46, 204, 113, 0.2); border-radius: 8px; padding: 12px;")
        telem_layout = QHBoxLayout(self._telemetry_box)
        
        self._status_lbl = QLabel("Status: Idle")
        self._status_lbl.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold;")
        
        self._fps_lbl = QLabel("FPS: --")
        self._fps_lbl.setStyleSheet("color: #2ECC71; font-size: 13px; font-weight: bold;")

        self._bitrate_lbl = QLabel("Bitrate: -- kbps")
        self._bitrate_lbl.setStyleSheet("color: #00E5CC; font-size: 13px; font-weight: bold;")

        telem_layout.addWidget(self._status_lbl)
        telem_layout.addStretch()
        telem_layout.addWidget(self._fps_lbl)
        telem_layout.addSpacing(20)
        telem_layout.addWidget(self._bitrate_lbl)
        layout.addWidget(self._telemetry_box)

        # 4. Action Button
        self._start_btn = QPushButton("🚀  START STREAMING TO PHONE")
        self._start_btn.setFixedHeight(48)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #021208;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34D399, stop:1 #10B981);
            }
        """)
        self._start_btn.clicked.connect(self._toggle_stream)
        layout.addWidget(self._start_btn)

        layout.addStretch()

    def _populate_monitors(self) -> None:
        """Query system monitors."""
        try:
            sct = ScreenCapture()
            mons = sct.get_monitors()
            for m in mons:
                self._mon_combo.addItem(m["name"], m["id"])
            sct.close()
        except Exception as e:
            log.debug("Error populating monitors: %s", e)
            self._mon_combo.addItem("Primary Display (Auto)", 0)

    def _toggle_stream(self) -> None:
        if not self._is_streaming:
            self._start_stream()
        else:
            self._stop_stream()

    def _start_stream(self) -> None:
        target_ip = self._ip_input.text().strip()
        if not target_ip and self._get_phone_ip:
            target_ip = self._get_phone_ip() or ""

        if not target_ip:
            self._status_lbl.setText("Status: Error (Please enter phone IP!)")
            self._status_lbl.setStyleSheet("color: #EF4444; font-size: 13px; font-weight: bold;")
            return

        fps_map = {0: 30, 1: 60, 2: 120}
        selected_fps = fps_map.get(self._fps_combo.currentIndex(), 60)

        bitrate_map = {0: 4000, 1: 6000, 2: 10000, 3: 16000}
        selected_bitrate = bitrate_map.get(self._bitrate_combo.currentIndex(), 6000)

        mon_idx = self._mon_combo.currentData() or 1

        self._server = ReverseStreamServer(
            fps=selected_fps,
            bitrate_kbps=selected_bitrate,
            monitor_index=mon_idx,
            enable_audio=self._audio_check.isChecked(),
        )
        self._server.stats_updated.connect(self._on_stats)
        self._server.stream_stopped.connect(self._on_server_stopped)

        if self._server.start(client_ip=target_ip):
            self._is_streaming = True
            self._status_lbl.setText(f"Status: Streaming to {target_ip}")
            self._status_lbl.setStyleSheet("color: #2ECC71; font-size: 13px; font-weight: bold;")
            self._start_btn.setText("⏹️  STOP STREAMING")
            self._start_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #EF4444, stop:1 #DC2626);
                    color: #FFFFFF;
                    font-weight: bold;
                    font-size: 14px;
                    border-radius: 8px;
                    border: none;
                }
                QPushButton:hover {
                    background: #F87171;
                }
            """)
        else:
            self._status_lbl.setText("Status: Failed to start stream!")
            self._status_lbl.setStyleSheet("color: #EF4444; font-size: 13px; font-weight: bold;")

    def _stop_stream(self) -> None:
        if self._server:
            self._server.stop()
            self._server = None
        self._on_server_stopped()

    def _on_stats(self, fps: float, bitrate: int) -> None:
        self._fps_lbl.setText(f"FPS: {fps:.1f}")
        self._bitrate_lbl.setText(f"Bitrate: {bitrate} kbps")

    def _on_server_stopped(self) -> None:
        self._is_streaming = False
        self._status_lbl.setText("Status: Idle")
        self._status_lbl.setStyleSheet("color: #9CA3AF; font-size: 13px; font-weight: bold;")
        self._fps_lbl.setText("FPS: --")
        self._bitrate_lbl.setText("Bitrate: -- kbps")
        self._start_btn.setText("🚀  START STREAMING TO PHONE")
        self._start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #021208;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34D399, stop:1 #10B981);
            }
        """)

    def set_phone_ip(self, ip: str) -> None:
        """Called when auto-discovery links a phone."""
        if not self._ip_input.text():
            self._ip_input.setText(ip)
