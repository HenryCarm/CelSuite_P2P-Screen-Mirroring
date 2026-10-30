"""
Collapsible card widget for hiding advanced/secondary UI controls.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QParallelAnimationGroup, QPropertyAnimation, QAbstractAnimation
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class CollapsibleCard(QFrame):
    """
    A modern rounded card with an expandable/collapsible content section.
    Helps reduce UI clutter by hiding advanced controls until clicked.
    """

    def __init__(self, title: str, expanded: bool = False) -> None:
        super().__init__()
        self.setObjectName("collapsible-card")
        self._is_expanded = expanded

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(0)

        # ── Toggle Header ─────────────────────────────────────────────
        self._toggle_button = QPushButton()
        self._toggle_button.setObjectName("collapsible-header")
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.setFlat(True)
        self._toggle_button.clicked.connect(self.toggle)

        header_layout = QHBoxLayout(self._toggle_button)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        self._title_label = QLabel(title)
        self._title_label.setObjectName("section-title")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        self._arrow_label = QLabel("▼" if expanded else "▶")
        self._arrow_label.setObjectName("collapsible-arrow")
        header_layout.addWidget(self._arrow_label)

        main_layout.addWidget(self._toggle_button)

        # ── Content Area ──────────────────────────────────────────────
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 12, 0, 4)
        self.content_layout.setSpacing(12)

        main_layout.addWidget(self.content_container)

        # Set initial visibility
        self.content_container.setVisible(expanded)

    def toggle(self) -> None:
        """Toggle content visibility."""
        self._is_expanded = not self._is_expanded
        self.content_container.setVisible(self._is_expanded)
        self._arrow_label.setText("▼" if self._is_expanded else "▶")

    def set_expanded(self, expanded: bool) -> None:
        """Explicitly set expansion state."""
        self._is_expanded = expanded
        self.content_container.setVisible(expanded)
        self._arrow_label.setText("▼" if expanded else "▶")

    def addWidget(self, widget: QWidget) -> None:
        """Helper to add widget to content container."""
        self.content_layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        """Helper to add layout to content container."""
        self.content_layout.addLayout(layout)
