"""
Dedicated full-window Logs tab for Scrcpy Heartbeat.

Displays real-time application and ADB logs with color-coding,
search/filtering, one-click copy, and live streaming from the Qt log bridge.
"""

from __future__ import annotations

import os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QApplication,
)

from src.config import AppConfig
from src.constants import LOG_FILE
from src.logger import get_logger, get_signal_bridge
from src.ui.styles import COLORS

log = get_logger(__name__)


class LogsTab(QWidget):
    """Full-screen live log viewer tab."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._auto_scroll = True
        self._filter_text = ""
        self._all_logs: list[str] = []

        self._build_ui()
        self._connect_signals()
        self._load_existing_logs()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # ── Top Header / Toolbar ─────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        title_lbl = QLabel("📜 Live System & ADB Logs")
        title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['text']};")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        # Filter Input
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("🔍 Filter logs...")
        self._filter_input.setFixedWidth(200)
        self._filter_input.textChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self._filter_input)

        # Auto-scroll toggle
        self._autoscroll_cb = QCheckBox("Auto-Scroll")
        self._autoscroll_cb.setChecked(True)
        self._autoscroll_cb.stateChanged.connect(self._on_autoscroll_changed)
        header_layout.addWidget(self._autoscroll_cb)

        # Copy Button
        self._copy_btn = QPushButton("📋 Copy All")
        self._copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent']};
                color: white;
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_light']};
            }}
        """)
        self._copy_btn.clicked.connect(self._copy_logs)
        header_layout.addWidget(self._copy_btn)

        # Clear Button
        self._clear_btn = QPushButton("🧹 Clear")
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_card']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: #E11D48;
                color: white;
            }}
        """)
        self._clear_btn.clicked.connect(self._clear_logs)
        header_layout.addWidget(self._clear_btn)

        # Refresh Button
        self._refresh_btn = QPushButton("🔄 Refresh")
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_card']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_button_hover']};
            }}
        """)
        self._refresh_btn.clicked.connect(self._load_existing_logs)
        header_layout.addWidget(self._refresh_btn)

        main_layout.addLayout(header_layout)

        # ── Fullscreen Text View ─────────────────────────────────────────
        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("Monospace", 10))
        self._text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0A0812;
                color: #E2E8F0;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 10px;
                selection-background-color: {COLORS['accent']};
                selection-color: #FFFFFF;
            }}
        """)
        main_layout.addWidget(self._text_edit)

        # Status feedback footer
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        main_layout.addWidget(self._status_lbl)

    def _connect_signals(self) -> None:
        """Connect live log messages to the UI viewer."""
        bridge = get_signal_bridge()
        bridge.log_message.connect(self._append_log_line)

    def _append_log_line(self, line: str) -> None:
        """Append a single log line in real time."""
        self._all_logs.append(line)
        if self._filter_text and self._filter_text.lower() not in line.lower():
            return

        self._text_edit.appendPlainText(line)
        if self._auto_scroll:
            self._text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _load_existing_logs(self) -> None:
        """Load logs from file."""
        log_path = self._config.get("log_file", LOG_FILE)
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                self._all_logs = [l.rstrip("\r\n") for l in lines]
                self._refilter_display()
                self._status_lbl.setText(f"Loaded {len(self._all_logs)} log lines from {log_path}")
            except Exception as e:
                self._status_lbl.setText(f"Error reading log file: {e}")
        else:
            self._text_edit.setPlainText("")
            self._status_lbl.setText("No log file found yet.")

    def _refilter_display(self) -> None:
        """Re-render visible logs based on current filter query."""
        if not self._filter_text:
            text = "\n".join(self._all_logs)
        else:
            q = self._filter_text.lower()
            filtered = [l for l in self._all_logs if q in l.lower()]
            text = "\n".join(filtered)

        self._text_edit.setPlainText(text)
        if self._auto_scroll:
            self._text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text.strip()
        self._refilter_display()

    def _on_autoscroll_changed(self, state: int) -> None:
        self._auto_scroll = (state == Qt.CheckState.Checked.value or state == 2)

    def _copy_logs(self) -> None:
        """Copy all displayed text or selected text to clipboard."""
        cursor = self._text_edit.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            label = "Selected logs copied!"
        else:
            text = self._text_edit.toPlainText()
            label = "All logs copied to clipboard! (📋)"

        cb = QApplication.clipboard()
        if cb:
            cb.setText(text)
            self._copy_btn.setText("✅ Copied!")
            self._status_lbl.setText(label)
            QTimer.singleShot(1500, lambda: self._copy_btn.setText("📋 Copy All"))

    def _clear_logs(self) -> None:
        """Clear the in-memory display and truncate log file."""
        self._all_logs.clear()
        self._text_edit.setPlainText("")
        log_path = self._config.get("log_file", LOG_FILE)
        try:
            if os.path.exists(log_path):
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("")
            self._status_lbl.setText("Logs cleared.")
        except Exception as e:
            self._status_lbl.setText(f"Failed to clear log file: {e}")
