"""
Animation utilities for ScrcpyUltimateLink.

Provides reusable animation helpers and custom animated widgets
for the Royal Nebula UI theme.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Property,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QPushButton,
    QWidget,
)


# ── Opacity Animations ────────────────────────────────────────────────────────


def fade_in(widget: QWidget, duration: int = 300) -> None:
    """Fade a widget in from transparent to fully opaque."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    # Keep reference so it doesn't get garbage collected
    widget._fade_anim = anim


def fade_out(widget: QWidget, duration: int = 300) -> None:
    """Fade a widget out from opaque to transparent."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    anim.start()
    widget._fade_anim = anim


# ── Glow Effect ───────────────────────────────────────────────────────────────


def apply_glow(widget: QWidget, color: str = "#7C3AED", radius: int = 15,
               offset: tuple = (0, 0)) -> QGraphicsDropShadowEffect:
    """Apply a colored glow shadow effect to a widget."""
    glow = QGraphicsDropShadowEffect(widget)
    glow.setColor(QColor(color))
    glow.setBlurRadius(radius)
    glow.setOffset(*offset)
    widget.setGraphicsEffect(glow)
    return glow


def flash_glow(widget: QWidget, color: str = "#7C3AED",
               duration: int = 600) -> None:
    """Briefly flash a glow effect on a widget, then fade it away."""
    glow = apply_glow(widget, color, radius=25)

    anim = QPropertyAnimation(glow, b"blurRadius")
    anim.setDuration(duration)
    anim.setStartValue(25)
    anim.setEndValue(8)
    anim.setEasingCurve(QEasingCurve.Type.OutQuad)
    anim.start()
    widget._flash_anim = anim


# ── Animated Push Button ──────────────────────────────────────────────────────


class AnimatedButton(QPushButton):
    """
    A QPushButton with a subtle press bounce animation.

    On press: button quickly shrinks slightly.
    On release: button bounces back to full size.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._scale = 1.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._animate_press()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._animate_release()
        super().mouseReleaseEvent(event)

    def _animate_press(self) -> None:
        """Shrink slightly on press."""
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(80)
        geo = self.geometry()
        dx = int(geo.width() * 0.02)
        dy = int(geo.height() * 0.02)
        anim.setStartValue(geo)
        anim.setEndValue(QRect(
            geo.x() + dx, geo.y() + dy,
            geo.width() - 2 * dx, geo.height() - 2 * dy,
        ))
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.start()
        self._press_anim = anim
        self._original_geo = geo

    def _animate_release(self) -> None:
        """Bounce back to original size on release."""
        if not hasattr(self, '_original_geo'):
            return
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(120)
        anim.setStartValue(self.geometry())
        anim.setEndValue(self._original_geo)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        anim.start()
        self._release_anim = anim


# ── Collapse / Expand Animation ───────────────────────────────────────────────


def animate_height(widget: QWidget, target_height: int,
                   duration: int = 250) -> None:
    """Smoothly animate a widget's maximum height."""
    anim = QPropertyAnimation(widget, b"maximumHeight")
    anim.setDuration(duration)
    anim.setStartValue(widget.maximumHeight())
    anim.setEndValue(target_height)
    anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
    anim.start()
    widget._height_anim = anim
