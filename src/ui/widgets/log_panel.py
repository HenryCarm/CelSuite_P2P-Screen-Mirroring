"""
Collapsible log panel widget for ScrcpyUltimateLink.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.logger import get_signal_bridge
from src.ui.animations import animate_height


class LogPanel(QGroupBox):
    """
    A collapsible log viewer that auto-scrolls and can be connected
    to the centralized logging system.

    Features smooth collapse/expand height animation.
    """

    def __init__(self, title: str = "📜  System Logs", max_height: int = 200) -> None:
        super().__init__(title)
        self._max_height = max_height

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Log text area
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMaximumHeight(max_height)
        layout.addWidget(self._log_area)

        # Button bar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._toggle_btn = QPushButton("▼  Collapse")
        self._toggle_btn.setObjectName("control-btn")
        self._toggle_btn.clicked.connect(self._toggle)

        copy_btn = QPushButton("📋  Copy")
        copy_btn.setObjectName("control-btn")
        copy_btn.clicked.connect(self._copy_logs)

        clear_btn = QPushButton("🗑  Clear")
        clear_btn.setObjectName("control-btn")
        clear_btn.clicked.connect(self._clear_logs)

        btn_layout.addWidget(self._toggle_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)

        self._collapsed = False

        # Connect to centralized logging bridge
        bridge = get_signal_bridge()
        bridge.log_message.connect(self.append)

    def append(self, message: str) -> None:
        """Append a log line and auto-scroll to bottom."""
        self._log_area.append(message)
        scrollbar = self._log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _toggle(self) -> None:
        """Toggle the log area visibility with smooth animation."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            animate_height(self._log_area, 0, duration=250)
            self._toggle_btn.setText("▶  Expand")
        else:
            animate_height(self._log_area, self._max_height, duration=250)
            self._toggle_btn.setText("▼  Collapse")

    def _copy_logs(self) -> None:
        """Copy all log text to the clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._log_area.toPlainText())

    def _clear_logs(self) -> None:
        """Clear the log display."""
        self._log_area.clear()
