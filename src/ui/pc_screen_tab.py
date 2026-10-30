"""
Mirror PC tab — the *actual* PC-to-phone screen mirror.

Shows a live local preview of exactly what the phone sees (TCP MJPEG via
:mod:`src.reverse_mirror.mirror_server`), plus Start/Stop, display picker,
framerate and quality controls. Phone side: open "Watch PC" (PCVideoScreen
in ``android/main.py``) which connects to port 5563.

The old "Mirror PC" tab only ever sent input (touchpad/mouse/keys) and never
displayed PC video on the phone — it is now honestly named "Control PC".
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig
from src.constants import DEFAULT_MIRROR_VIDEO_PORT
from src.logger import get_logger
from src.reverse_mirror.mirror_server import HAS_PIL, PCMirrorServer
from src.reverse_mirror.screen_capture import ScreenCapture
from src.reverse_mirror.stream_server import ReverseStreamServer
from src.ui.icons import set_button_icon

log = get_logger(__name__)


class PCScreenTab(QWidget):
    """Live PC-screen streaming to the phone with local preview."""

    def __init__(
        self, config: AppConfig,
        get_phone_ip: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._get_phone_ip = get_phone_ip
        self._mirror: Optional[PCMirrorServer] = None
        self._input_only: Optional[ReverseStreamServer] = None
        self._is_live = False
        self._build_ui()
        # Automatically launch low-overhead mirror listener so port 5563 is ready when phone connects
        QTimer.singleShot(500, self._start)

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Mirror PC Screen to Phone")
        header.setStyleSheet("color: #2ECC71; font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        sub = QLabel(
            f"Live MJPEG stream on TCP {DEFAULT_MIRROR_VIDEO_PORT}. "
            "On the phone open Watch PC. Touch on the phone controls this PC."
        )
        sub.setStyleSheet("color: #A7F3D0; font-size: 13px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        if not HAS_PIL:
            warn = QLabel("Pillow is missing — install it (pip install Pillow) to enable mirroring.")
            warn.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold;")
            layout.addWidget(warn)

        cfg_box = QGroupBox("Stream Settings")
        cfg_layout = QVBoxLayout(cfg_box)
        cfg_layout.setSpacing(12)

        mon_row = QHBoxLayout()
        mon_row.addWidget(QLabel("Display:"))
        self._mon_combo = QComboBox()
        self._populate_monitors()
        mon_row.addWidget(self._mon_combo, 1)
        cfg_layout.addLayout(mon_row)

        perf_row = QHBoxLayout()
        perf_row.addWidget(QLabel("Framerate:"))
        self._fps_combo = QComboBox()
        self._fps_combo.addItems(["15 FPS", "30 FPS", "60 FPS"])
        self._fps_combo.setCurrentIndex(1)
        perf_row.addWidget(self._fps_combo)
        perf_row.addWidget(QLabel("Quality:"))
        self._quality = QSlider(Qt.Orientation.Horizontal)
        self._quality.setRange(30, 95)
        self._quality.setValue(int(self._config.get("pc_mirror_quality", 70)))
        self._quality.setMaximumWidth(160)
        self._quality.valueChanged.connect(
            lambda v: self._config.__setitem__("pc_mirror_quality", v)
        )
        self._quality_lbl = QLabel(f"{self._quality.value()}%")
        self._quality.valueChanged.connect(
            lambda v: self._quality_lbl.setText(f"{v}%")
        )
        perf_row.addWidget(self._quality, 1)
        perf_row.addWidget(self._quality_lbl)
        cfg_layout.addLayout(perf_row)

        self._input_check = QCheckBox("Allow phone touch/keyboard to control this PC")
        self._input_check.setChecked(True)
        cfg_layout.addWidget(self._input_check)

        layout.addWidget(cfg_box)

        # Preview
        self._preview = QLabel("Preview idle — press Start")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(260)
        self._preview.setStyleSheet(
            "background: rgba(10, 20, 14, 0.75); border: 1px solid rgba(16,185,129,0.3);"
            " border-radius: 8px; color: #9CA3AF;"
        )
        layout.addWidget(self._preview, 1)

        # Telemetry
        telem = QFrame()
        telem_layout = QHBoxLayout(telem)
        self._status_lbl = QLabel("Status: Idle")
        self._fps_lbl = QLabel("FPS: --")
        self._kbps_lbl = QLabel("Rate: -- kbps")
        self._peer_lbl = QLabel("Viewer: none")
        for w in (self._status_lbl, self._fps_lbl, self._kbps_lbl, self._peer_lbl):
            w.setStyleSheet("color: #9CA3AF; font-size: 12px; font-weight: bold;")
            telem_layout.addWidget(w)
        telem_layout.addStretch()
        layout.addWidget(telem)

        # Actions
        row = QHBoxLayout()
        self._start_btn = QPushButton("Start Mirror")
        set_button_icon(self._start_btn, "play")
        self._start_btn.setFixedHeight(46)
        self._start_btn.clicked.connect(self._toggle)
        row.addWidget(self._start_btn, 1)
        layout.addLayout(row)
        layout.addStretch()

    def _populate_monitors(self) -> None:
        try:
            sct = ScreenCapture()
            for m in sct.get_monitors():
                self._mon_combo.addItem(m["name"], m["id"])
            sct.close()
        except Exception:
            self._mon_combo.addItem("Primary Display (Auto)", 1)

    # ── Stream control ────────────────────────────────────────────────

    def _toggle(self) -> None:
        if not self._is_live:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        fps = (15, 30, 60)[self._fps_combo.currentIndex()]
        mon = self._mon_combo.currentData()
        try:
            mon_idx = int(mon) if mon is not None else 1
        except (TypeError, ValueError):
            mon_idx = 1
        self._mirror = PCMirrorServer(
            fps=fps,
            quality=int(self._quality.value()),
            monitor_index=mon_idx,
        )
        self._mirror.frame_ready.connect(self._on_frame)
        self._mirror.stats_updated.connect(self._on_stats)
        self._mirror.client_connected.connect(self._on_peer)
        self._mirror.client_disconnected.connect(
            lambda: self._peer_lbl.setText("Viewer: none")
        )
        if not self._mirror.start():
            self._status_lbl.setText("Status: Failed (see Logs)")
            self._mirror = None
            return
        if self._input_check.isChecked():
            # Input-only server: phone touch → this PC (no H.264 needed).
            self._input_only = ReverseStreamServer(
                fps=30, bitrate_kbps=2000, monitor_index=mon_idx,
                enable_audio=False, enable_video=False,
            )
            target = self._ip_hint()
            if target:
                self._input_only.set_client(target)
            # Bind input socket without needing a video client:
            self._input_only.bind_input_only()
        self._is_live = True
        self._start_btn.setText("Stop Mirror")
        set_button_icon(self._start_btn, "stop")
        self._status_lbl.setText(
            f"Status: Live on port {DEFAULT_MIRROR_VIDEO_PORT} — open Watch PC on phone"
        )
        log.info("PC screen mirror started (%d fps)", fps)

    def _stop(self) -> None:
        for srv in (self._mirror, self._input_only):
            try:
                if srv:
                    srv.stop()
            except Exception:
                pass
        self._mirror = None
        self._input_only = None
        self._is_live = False
        self._start_btn.setText("Start Mirror")
        set_button_icon(self._start_btn, "play")
        self._status_lbl.setText("Status: Idle")
        self._fps_lbl.setText("FPS: --")
        self._kbps_lbl.setText("Rate: -- kbps")
        self._peer_lbl.setText("Viewer: none")
        self._preview.setText("Preview idle — press Start")
        self._preview.setPixmap(QPixmap())

    def _ip_hint(self) -> Optional[str]:
        try:
            if self._get_phone_ip:
                return self._get_phone_ip()
        except Exception:
            pass
        return None

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_frame(self, jpg: bytes, w: int, h: int) -> None:
        pm = QPixmap()
        if pm.loadFromData(jpg, "JPG"):
            self._preview.setPixmap(
                pm.scaled(
                    self._preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )

    def _on_stats(self, fps: float, kbps: int) -> None:
        self._fps_lbl.setText(f"FPS: {fps:.1f}")
        self._kbps_lbl.setText(f"Rate: {kbps} kbps")

    def _on_peer(self, ip: str) -> None:
        self._peer_lbl.setText(f"Viewer: {ip}")

    def cleanup(self) -> None:
        self._stop()
