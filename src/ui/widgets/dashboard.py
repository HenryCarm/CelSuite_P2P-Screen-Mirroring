"""
Live hardware dashboard widget for ScrcpyUltimateLink.

Uses a grid of StatCard widgets to display device metrics
with glassmorphic styling and glow-on-update effects.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)

from src.ui.widgets.stat_card import StatCard


class DashboardWidget(QGroupBox):
    """
    Displays live device hardware info in a 2×3 grid of stat cards:
    Model, Android version, Battery, Temperature, Resolution, Latency.
    """

    def __init__(self) -> None:
        super().__init__("\U0001f4ca  Live Hardware Dashboard")

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # ── Stat card grid (2 columns × 3 rows) ──────────────────────
        grid = QGridLayout()
        grid.setSpacing(10)

        self._model_card = StatCard(icon="📱", label="Model", value="—")
        self._android_card = StatCard(icon="🤖", label="Android", value="—")
        self._battery_card = StatCard(icon="🔋", label="Battery", value="—")
        self._temp_card = StatCard(icon="🌡", label="Temperature", value="—")
        self._res_card = StatCard(icon="🖥", label="Resolution", value="—")
        self._latency_card = StatCard(icon="📡", label="WiFi Latency", value="—")

        grid.addWidget(self._model_card, 0, 0)
        grid.addWidget(self._android_card, 0, 1)
        grid.addWidget(self._battery_card, 1, 0)
        grid.addWidget(self._temp_card, 1, 1)
        grid.addWidget(self._res_card, 2, 0)
        grid.addWidget(self._latency_card, 2, 1)

        main_layout.addLayout(grid)

        # ── Refresh button ────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.refresh_btn = QPushButton("\U0001f504  Refresh Dashboard")
        self.refresh_btn.setObjectName("control-btn")
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

    def update_info(self, info: dict) -> None:
        """Update dashboard cards from a hardware info dict."""
        if "error" in info:
            err = str(info["error"])
            self._model_card.set_value("Error")
            self._android_card.set_value("Check Logs")
            self._battery_card.set_value(err[:14])
            return

        self._model_card.set_value(info.get("model", "—"))
        self._android_card.set_value(info.get("android_version", "—"))

        battery = info.get("battery_level", "—")
        charging = info.get("charging", "")
        battery_text = f"{battery}"
        if charging:
            battery_text += f" ({charging})"
        self._battery_card.set_value(battery_text)

        self._temp_card.set_value(info.get("temperature", "—"))
        self._res_card.set_value(info.get("resolution", "—"))

    def update_latency(self, latency_ms: float | None) -> None:
        """Update the latency card with color-coded value."""
        if latency_ms is not None:
            value = f"{latency_ms:.1f} ms"
            # Color-code: green < 50ms, amber < 150ms, red > 150ms
            if latency_ms < 50:
                self._latency_card._icon_label.setText("📡")
            elif latency_ms < 150:
                self._latency_card._icon_label.setText("📡")
            else:
                self._latency_card._icon_label.setText("📡")
            self._latency_card.set_value(value)
        else:
            self._latency_card.set_value("Timeout")

    def reset(self) -> None:
        """Reset all cards to default values."""
        self._model_card.set_value("—")
        self._android_card.set_value("—")
        self._battery_card.set_value("—")
        self._temp_card.set_value("—")
        self._res_card.set_value("—")
        self._latency_card.set_value("—")
