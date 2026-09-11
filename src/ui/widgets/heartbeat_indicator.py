"""
Animated heartbeat / connection pulse indicator for ScrcpyUltimateLink.

Displays concentric rings that pulse outward to indicate an active
connection heartbeat. Color changes based on connection state.
"""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Qt, QTimer, Property
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.ui.styles import COLORS


class HeartbeatIndicator(QWidget):
    """
    Animated concentric ring pulse indicator.

    States:
        - disconnected: Red dot, no pulse
        - discovering:  Amber dot, slow pulse
        - connected:    Green dot, steady pulse
        - error:        Red dot, fast flicker
    """

    # State → (center_color, ring_color)
    STATE_COLORS = {
        "disconnected": ("#EF4444", "#EF444440"),
        "discovering": ("#F59E0B", "#F59E0B50"),
        "connecting": ("#F59E0B", "#F59E0B50"),
        "connected": ("#10B981", "#10B98160"),
        "mirroring": ("#10B981", "#10B98160"),
        "error": ("#EF4444", "#EF444440"),
    }

    def __init__(self, size: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

        self._center_color = QColor(COLORS["error"])
        self._ring_color = QColor("#EF444440")
        self._ring_radius = 0.0
        self._ring_opacity = 1.0
        self._state = "disconnected"

        # Pulse animation for ring expansion
        self._pulse_anim = QPropertyAnimation(self, b"ringRadius")
        self._pulse_anim.setDuration(1500)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(float(size // 2))
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._pulse_anim.finished.connect(self._on_pulse_finished)

        # Opacity animation for ring fade
        self._fade_anim = QPropertyAnimation(self, b"ringOpacity")
        self._fade_anim.setDuration(1500)
        self._fade_anim.setStartValue(0.8)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        self._pulsing = False

    # ── Qt Properties ─────────────────────────────────────────────────

    @Property(float)
    def ringRadius(self) -> float:  # noqa: N802
        return self._ring_radius

    @ringRadius.setter
    def ringRadius(self, value: float) -> None:  # noqa: N802
        self._ring_radius = value
        self.update()

    @Property(float)
    def ringOpacity(self) -> float:  # noqa: N802
        return self._ring_opacity

    @ringOpacity.setter
    def ringOpacity(self, value: float) -> None:  # noqa: N802
        self._ring_opacity = value
        self.update()

    # ── State Control ─────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Change the indicator state and update colors/animation."""
        state = state.lower()
        if state == self._state:
            return

        self._state = state
        colors = self.STATE_COLORS.get(state, self.STATE_COLORS["disconnected"])
        self._center_color = QColor(colors[0])
        self._ring_color = QColor(colors[1])

        if state in ("connected", "mirroring"):
            self._start_pulse()
        elif state in ("discovering", "connecting"):
            self._start_pulse()
        else:
            self._stop_pulse()

        self.update()

    def _start_pulse(self) -> None:
        """Begin the pulse animation loop."""
        if self._pulsing:
            return
        self._pulsing = True
        self._pulse_anim.start()
        self._fade_anim.start()

    def _stop_pulse(self) -> None:
        """Stop the pulse animation."""
        self._pulsing = False
        self._pulse_anim.stop()
        self._fade_anim.stop()
        self._ring_radius = 0.0
        self._ring_opacity = 0.0
        self.update()

    def _on_pulse_finished(self) -> None:
        """Restart pulse loop if still active."""
        if self._pulsing:
            QTimer.singleShot(200, self._restart_pulse)

    def _restart_pulse(self) -> None:
        """Restart the pulse animation cycle."""
        if self._pulsing:
            self._ring_radius = 0.0
            self._ring_opacity = 0.8
            self._pulse_anim.start()
            self._fade_anim.start()

    # ── Painting ──────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        """Draw the center dot and expanding ring."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() / 2
        center_y = self.height() / 2
        dot_radius = self._size * 0.2

        # Draw expanding ring (if pulsing)
        if self._ring_radius > 0 and self._ring_opacity > 0:
            ring_color = QColor(self._ring_color)
            ring_color.setAlphaF(self._ring_opacity * 0.6)
            pen = QPen(ring_color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                int(center_x - self._ring_radius),
                int(center_y - self._ring_radius),
                int(self._ring_radius * 2),
                int(self._ring_radius * 2),
            )

        # Draw center dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._center_color)
        painter.drawEllipse(
            int(center_x - dot_radius),
            int(center_y - dot_radius),
            int(dot_radius * 2),
            int(dot_radius * 2),
        )

        # Draw subtle inner glow
        glow_color = QColor(self._center_color)
        glow_color.setAlphaF(0.3)
        painter.setBrush(glow_color)
        glow_r = dot_radius * 1.6
        painter.drawEllipse(
            int(center_x - glow_r),
            int(center_y - glow_r),
            int(glow_r * 2),
            int(glow_r * 2),
        )

        painter.end()
