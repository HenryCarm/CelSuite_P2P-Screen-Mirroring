"""
Custom glassmorphic container widget to replace QGroupBox.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SectionCard(QFrame):
    """
    A modern, rounded container card with an optional title header.
    Replaces the default QGroupBox to provide a breathable, premium aesthetic.
    """

    def __init__(self, title: str | None = None) -> None:
        super().__init__()
        self.setObjectName("section-card")
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(20, 20, 20, 20)
        self._main_layout.setSpacing(16)
        
        if title:
            header_label = QLabel(title)
            header_label.setObjectName("section-title")
            self._main_layout.addWidget(header_label)
            
            # Subtle separator
            separator = QFrame()
            separator.setObjectName("section-separator")
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            separator.setFixedHeight(1)
            self._main_layout.addWidget(separator)
            
        # Inner container for the actual content
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 4, 0, 0)
        self.content_layout.setSpacing(12)
        
        self._main_layout.addWidget(self.content_container)
    
    def addWidget(self, widget: QWidget) -> None:
        """Helper to add widgets directly to the inner layout."""
        self.content_layout.addWidget(widget)
        
    def addLayout(self, layout) -> None:
        """Helper to add layouts directly to the inner layout."""
        self.content_layout.addLayout(layout)
