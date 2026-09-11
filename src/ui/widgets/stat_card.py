"""
Glassmorphic stat card widget for ScrcpyUltimateLink.

Displays a single metric with icon, value, and label inside
a visually rich card with glow-on-update effects.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from src.ui.animations import flash_glow
from src.ui.styles import COLORS


class StatCard(QFrame):
    """
    A glassmorphic stat card showing an icon, value, and label.

    The card briefly glows when the value is updated.
    """

    def __init__(
        self,
        icon: str = "📊",
        label: str = "Metric",
        value: str = "—",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stat-card")
        self.setMinimumHeight(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        # Icon
        self._icon_label = QLabel(icon)
        self._icon_label.setStyleSheet("font-size: 24px; background: transparent;")
        self._icon_label.setFixedWidth(36)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        # Value + Label stack
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self._value_label = QLabel(value)
        self._value_label.setObjectName("stat-value")

        self._label_label = QLabel(label.upper())
        self._label_label.setObjectName("stat-label")

        text_layout.addWidget(self._value_label)
        text_layout.addWidget(self._label_label)
        layout.addLayout(text_layout)
        layout.addStretch()

        self._last_value = value

    def set_value(self, value: str) -> None:
        """Update the displayed value, triggering a glow if changed."""
        if value != self._last_value:
            self._value_label.setText(value)
            self._last_value = value
            # Flash glow on value change
            try:
                flash_glow(self, COLORS["accent"], duration=500)
            except RuntimeError:
                pass  # Widget may be in layout transition

    def set_icon(self, icon: str) -> None:
        """Update the card icon."""
        self._icon_label.setText(icon)

    def set_label(self, label: str) -> None:
        """Update the card label text."""
        self._label_label.setText(label.upper())

    def value(self) -> str:
        """Return the current value text."""
        return self._value_label.text()
