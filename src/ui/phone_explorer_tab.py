"""
Phone Storage Explorer Tab for CelSuite Desktop.

Allows browsing, downloading (pulling), and uploading (pushing) files and folders
directly to/from the connected Android device over ADB with an emerald liquid glass UI.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from typing import Callable, List, Optional

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig
from src.constants import format_size, get_file_icon
from src.logger import get_logger
from src.networking import adb
from src.ui.animations import AnimatedButton

log = get_logger(__name__)


class PhoneExplorerTab(QWidget):
    """Emerald-glass ADB Phone File & Storage Explorer."""

    # Signals for thread-safe GUI updates
    _sig_listing_ready = Signal(str, list)  # current_path, items
    _sig_op_finished = Signal(bool, str)     # success, message
    _sig_progress_status = Signal(str)       # status text

    def __init__(
        self,
        config: AppConfig,
        get_phone_ip: Optional[Callable[[], Optional[str]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._get_phone_ip = get_phone_ip
        self._current_path = "/sdcard"
        self._history: List[str] = ["/sdcard"]
        self._history_idx = 0
        self._current_items: list[dict] = []
        self._is_busy = False

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        #  1. Header & Title 
        header_box = QHBoxLayout()
        title_lbl = QLabel("Phone Storage Explorer (ADB)")
        title_lbl.setStyleSheet("color: #10B981; font-size: 18px; font-weight: bold;")
        header_box.addWidget(title_lbl)

        header_box.addStretch()

        self._conn_badge = QLabel(" Ready")
        self._conn_badge.setStyleSheet(
            "color: #34D399; font-size: 12px; font-weight: bold; "
            "background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.35); "
            "border-radius: 6px; padding: 4px 10px;"
        )
        header_box.addWidget(self._conn_badge)
        main_layout.addLayout(header_box)

        #  2. Quick Access Bookmarks Row 
        bookmarks_box = QHBoxLayout()
        bookmarks_box.setSpacing(8)

        bookmarks = [
            (" /sdcard", "/sdcard"),
            (" Downloads", "/sdcard/Download"),
            (" Camera", "/sdcard/DCIM/Camera"),
            (" Pictures", "/sdcard/Pictures"),
            (" Music", "/sdcard/Music"),
            (" Movies", "/sdcard/Movies"),
            (" Documents", "/sdcard/Documents"),
        ]

        for label, path in bookmarks:
            btn = QPushButton(label)
            btn.setStyleSheet("""QPushButton {
                    background-color: rgba(16, 32, 22, 0.65);
                    color: #A7F3D0;
                    border: 1px solid rgba(16, 185, 129, 0.25);
                    border-radius: 8px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 600;
                    min-height: 28px;
                }
                QPushButton:hover {
                    background-color: rgba(24, 48, 34, 0.85);
                    border-color: #10B981;
                    color: #FFFFFF;
                }
            """)
            btn.clicked.connect(lambda _, p=path: self.navigate_to(p))
            bookmarks_box.addWidget(btn)

        bookmarks_box.addStretch()
        main_layout.addLayout(bookmarks_box)

        #  3. Navigation Bar (Back, Up, Path Edit, Refresh) 
        nav_box = QHBoxLayout()
        nav_box.setSpacing(8)

        self._btn_back = AnimatedButton(" Back")
        self._btn_back.setFixedWidth(75)
        self._btn_back.clicked.connect(self._go_back)

        self._btn_up = AnimatedButton(" Up")
        self._btn_up.setFixedWidth(65)
        self._btn_up.clicked.connect(self._go_up)

        self._path_input = QLineEdit(self._current_path)
        self._path_input.setStyleSheet("""QLineEdit {
                background: rgba(10, 20, 14, 0.75);
                color: #F0FDF4;
                border: 1.5px solid rgba(16, 185, 129, 0.35);
                border-radius: 8px;
                padding: 6px 12px;
                font-family: monospace;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #10B981;
            }
        """)
        self._path_input.returnPressed.connect(self._on_path_entered)

        self._btn_go = QPushButton("Go")
        self._btn_go.setFixedWidth(50)
        self._btn_go.clicked.connect(self._on_path_entered)

        self._btn_refresh = QPushButton(" Refresh")
        self._btn_refresh.setFixedWidth(90)
        self._btn_refresh.clicked.connect(self.refresh)

        nav_box.addWidget(self._btn_back)
        nav_box.addWidget(self._btn_up)
        nav_box.addWidget(self._path_input)
        nav_box.addWidget(self._btn_go)
        nav_box.addWidget(self._btn_refresh)
        main_layout.addLayout(nav_box)

        #  4. Action Buttons Toolbar (Download, Upload, New Folder, Delete)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        self._btn_pull = QPushButton("Download to PC")
        self._btn_pull.setStyleSheet("""QPushButton {
                background-color: #059669;
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 8px;
                padding: 7px 16px;
            }
            QPushButton:hover { background-color: #10B981; }
        """)
        self._btn_pull.clicked.connect(self._download_selected)

        self._btn_push_file = QPushButton("Upload File(s)")
        self._btn_push_file.setStyleSheet("""QPushButton {
                background-color: rgba(22, 42, 30, 0.80);
                color: #F0FDF4;
                border: 1px solid #10B981;
                border-radius: 8px;
                padding: 7px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(34, 64, 46, 0.95); }
        """)
        self._btn_push_file.clicked.connect(self._upload_files)

        self._btn_push_folder = QPushButton("Upload Folder Intact")
        self._btn_push_folder.setStyleSheet("""QPushButton {
                background-color: rgba(22, 42, 30, 0.80);
                color: #F0FDF4;
                border: 1px solid #10B981;
                border-radius: 8px;
                padding: 7px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(34, 64, 46, 0.95); }
        """)
        self._btn_push_folder.clicked.connect(self._upload_folder)

        self._btn_mkdir = QPushButton("New Folder")
        self._btn_mkdir.clicked.connect(self._create_folder)

        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setStyleSheet("""QPushButton {
                background-color: rgba(60, 20, 20, 0.65);
                color: #FCA5A5;
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 8px;
                padding: 7px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #EF4444;
                color: #FFFFFF;
            }
        """)
        self._btn_delete.clicked.connect(self._delete_selected)

        # Search filter box
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(" Filter files...")
        self._search_input.setFixedWidth(180)
        self._search_input.setStyleSheet("""QLineEdit {
                background: rgba(10, 20, 14, 0.60);
                color: #F0FDF4;
                border: 1px solid rgba(16, 185, 129, 0.25);
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
            }
        """)
        self._search_input.textChanged.connect(self._apply_filter)

        action_bar.addWidget(self._btn_pull)
        action_bar.addWidget(self._btn_push_file)
        action_bar.addWidget(self._btn_push_folder)
        action_bar.addWidget(self._btn_mkdir)
        action_bar.addWidget(self._btn_delete)
        action_bar.addStretch()
        action_bar.addWidget(self._search_input)
        main_layout.addLayout(action_bar)

        #  5. PC Download Directory Selector Row 
        dest_box = QHBoxLayout()
        dest_box.setSpacing(8)
        dest_lbl = QLabel(" Save Downloads to:")
        dest_lbl.setStyleSheet("color: #A7F3D0; font-size: 12px; font-weight: bold;")
        
        default_pc_dir = self._config.get("pc_download_dir", os.path.expanduser("~/Downloads"))
        if not os.path.exists(default_pc_dir):
            default_pc_dir = os.path.expanduser("~")
        self._dest_dir_input = QLineEdit(default_pc_dir)
        self._dest_dir_input.setStyleSheet("""QLineEdit {
                background: rgba(10, 20, 14, 0.70);
                color: #F0FDF4;
                border: 1px solid rgba(16, 185, 129, 0.30);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 12px;
            }
        """)
        self._dest_dir_input.textChanged.connect(self._on_dest_dir_changed)

        btn_browse_dest = QPushButton(" Browse PC...")
        btn_browse_dest.setStyleSheet("""QPushButton {
                background-color: rgba(20, 42, 30, 0.85);
                color: #A7F3D0;
                border: 1px solid rgba(16, 185, 129, 0.35);
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(30, 60, 42, 0.95); color: #FFFFFF; }
        """)
        btn_browse_dest.clicked.connect(self._browse_dest_dir)

        dest_box.addWidget(dest_lbl)
        dest_box.addWidget(self._dest_dir_input, 1)
        dest_box.addWidget(btn_browse_dest)
        main_layout.addLayout(dest_box)

        #  6. File Table View (NoEditTriggers so double click opens instantly!) 
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified Date"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.setStyleSheet("""QTableWidget {
                background-color: rgba(10, 22, 16, 0.70);
                border: 1px solid rgba(16, 185, 129, 0.30);
                border-radius: 10px;
                color: #F0FDF4;
                gridline-color: rgba(16, 185, 129, 0.15);
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: rgba(16, 32, 22, 0.90);
                color: #34D399;
                font-weight: bold;
                border: none;
                border-bottom: 2px solid #10B981;
                padding: 6px 10px;
            }
            QTableWidget::item:selected {
                background-color: rgba(16, 185, 129, 0.35);
                color: #FFFFFF;
            }
            QTableWidget::item:hover {
                background-color: rgba(24, 48, 34, 0.50);
            }
        """)
        main_layout.addWidget(self._table)

        #  6. Status & Progress Bar 
        status_box = QHBoxLayout()
        self._status_lbl = QLabel("0 items")
        self._status_lbl.setStyleSheet("color: #9CA3AF; font-size: 12px;")

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 0)  # indeterminate when active
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet("""QProgressBar {
                background: rgba(10, 20, 14, 0.5);
                border-radius: 4px;
                border: none;
            }
            QProgressBar::chunk {
                background: #10B981;
                border-radius: 4px;
            }
        """)

        status_box.addWidget(self._status_lbl)
        status_box.addStretch()
        status_box.addWidget(self._progress_bar)
        main_layout.addLayout(status_box)

    def _connect_signals(self) -> None:
        self._sig_listing_ready.connect(self._on_listing_ready)
        self._sig_op_finished.connect(self._on_op_finished)
        self._sig_progress_status.connect(self._on_progress_status)

    #  Device Resolution 

    def _get_target(self) -> tuple[Optional[str], int]:
        ip = None
        if self._get_phone_ip:
            ip = self._get_phone_ip()
        if not ip:
            ip, port = adb.get_connected_phone(self._config)
        else:
            port = self._config.get("adb_port", 5555)
        return ip, port or 5555

    #  Navigation & Listing 

    def navigate_to(self, path: str) -> None:
        """Change directory to target path."""
        path = path.strip()
        if not path:
            path = "/sdcard"
        if not path.startswith("/"):
            path = "/" + path
        while "//" in path:
            path = path.replace("//", "/")
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        if path != self._current_path:
            if self._history_idx < len(self._history) - 1:
                self._history = self._history[: self._history_idx + 1]
            self._history.append(path)
            self._history_idx = len(self._history) - 1

        self._current_path = path
        self._path_input.setText(path)
        self.refresh()

    def refresh(self) -> None:
        """Fetch directory listing in background thread."""
        ip, port = self._get_target()
        if not ip:
            self._conn_badge.setText(" Not Connected")
            self._conn_badge.setStyleSheet(
                "color: #F59E0B; font-size: 12px; font-weight: bold; "
                "background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.35); "
                "border-radius: 6px; padding: 4px 10px;"
            )
            self._status_lbl.setText("No device linked. Please connect phone first.")
            return

        self._conn_badge.setText(f" {ip}:{port}")
        self._conn_badge.setStyleSheet(
            "color: #10B981; font-size: 12px; font-weight: bold; "
            "background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.35); "
            "border-radius: 6px; padding: 4px 10px;"
        )

        self._progress_bar.setVisible(True)
        self._status_lbl.setText(f"Loading {self._current_path}...")

        target_path = self._current_path

        def worker():
            items = adb.list_phone_dir(self._config, target_path, ip, port)
            self._sig_listing_ready.emit(target_path, items)

        threading.Thread(target=worker, daemon=True).start()

    def _on_listing_ready(self, path: str, items: list[dict]) -> None:
        self._progress_bar.setVisible(False)
        self._current_items = items
        self._current_path = path
        self._path_input.setText(path)
        self._populate_table(items)

    def _populate_table(self, items: list[dict]) -> None:
        self._table.setRowCount(0)
        filter_text = self._search_input.text().lower().strip()

        # Sort: directories first, then alphabetically
        sorted_items = sorted(
            items,
            key=lambda x: (not x.get("is_dir", False), x.get("name", "").lower()),
        )

        row_idx = 0
        total_folders = 0
        total_files = 0
        total_bytes = 0

        for item in sorted_items:
            name = item.get("name", "")
            if filter_text and filter_text not in name.lower():
                continue

            is_dir = item.get("is_dir", False)
            size = item.get("size", 0)
            date_str = item.get("date", "")

            if is_dir:
                total_folders += 1
                icon_str = "[DIR]"
                size_str = "--"
                type_str = "Folder"
            else:
                total_files += 1
                total_bytes += size
                icon_str = get_file_icon(name)
                size_str = format_size(size)
                ext = os.path.splitext(name)[1].upper()
                type_str = f"{ext[1:]} File" if ext else "File"
            self._table.insertRow(row_idx)

            # Name Item
            name_item = QTableWidgetItem(f"{icon_str}  {name}")
            name_item.setData(Qt.ItemDataRole.UserRole, item)
            self._table.setItem(row_idx, 0, name_item)

            # Size Item
            size_item = QTableWidgetItem(size_str)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_idx, 1, size_item)

            # Type Item
            type_item = QTableWidgetItem(type_str)
            self._table.setItem(row_idx, 2, type_item)

            # Date Item
            date_item = QTableWidgetItem(date_str)
            self._table.setItem(row_idx, 3, date_item)

            row_idx += 1

        self._status_lbl.setText(
            f"{total_folders} folders, {total_files} files ({format_size(total_bytes)})"
        )

    def _apply_filter(self) -> None:
        self._populate_table(self._current_items)

    def _go_back(self) -> None:
        if self._history_idx > 0:
            self._history_idx -= 1
            path = self._history[self._history_idx]
            self._current_path = path
            self._path_input.setText(path)
            self.refresh()

    def _go_up(self) -> None:
        if self._current_path in ("/", "/sdcard"):
            return
        parent = os.path.dirname(self._current_path)
        if not parent:
            parent = "/"
        self.navigate_to(parent)

    def _on_path_entered(self) -> None:
        target = self._path_input.text().strip()
        if target:
            self.navigate_to(target)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        item_data = self._get_item_data_at_row(row)
        if not item_data:
            return

        if item_data.get("is_dir", False):
            name = item_data.get("name", "")
            new_path = os.path.join(self._current_path, name)
            self.navigate_to(new_path)
        else:
            self._download_selected()

    def _get_item_data_at_row(self, row: int) -> Optional[dict]:
        table_item = self._table.item(row, 0)
        if table_item:
            return table_item.data(Qt.ItemDataRole.UserRole)
        return None

    def _get_selected_items(self) -> list[dict]:
        selected_rows = set(index.row() for index in self._table.selectedIndexes())
        items = []
        for r in sorted(selected_rows):
            data = self._get_item_data_at_row(r)
            if data:
                items.append(data)
        return items

    def _on_dest_dir_changed(self, text: str) -> None:
        path = text.strip()
        if os.path.isdir(path):
            self._config["pc_download_dir"] = path

    def _browse_dest_dir(self) -> None:
        current = self._dest_dir_input.text().strip() or os.path.expanduser("~/Downloads")
        chosen = QFileDialog.getExistingDirectory(self, "Select PC Download Location", current)
        if chosen:
            self._dest_dir_input.setText(chosen)
            self._config["pc_download_dir"] = chosen

    #  Context Menu 

    def _show_context_menu(self, pos: QPoint) -> None:
        selected = self._get_selected_items()
        if not selected:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""QMenu {
                background-color: rgba(16, 32, 22, 0.95);
                border: 1px solid #10B981;
                border-radius: 8px;
                padding: 4px;
                color: #F0FDF4;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #10B981;
                color: #021208;
                font-weight: bold;
            }
        """)

        act_pull = menu.addAction(" Download to PC")
        act_pull.triggered.connect(self._download_selected)

        if len(selected) == 1:
            act_rename = menu.addAction(" Rename on Phone")
            act_rename.triggered.connect(self._rename_selected)

        menu.addSeparator()

        act_delete = menu.addAction(" Delete from Phone")
        act_delete.triggered.connect(self._delete_selected)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _rename_selected(self) -> None:
        selected = self._get_selected_items()
        if len(selected) != 1:
            return
        item = selected[0]
        old_name = item.get("name", "")
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "Rename", f"Rename '{old_name}' to:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        new_name = new_name.strip()
        old_remote = os.path.join(self._current_path, old_name)
        new_remote = os.path.join(self._current_path, new_name)

        ip, port = self._get_target()
        if not ip:
            return

        self._progress_bar.setVisible(True)

        def worker():
            ok, msg = adb.rename_on_phone(self._config, old_remote, new_remote, ip, port)
            self._sig_op_finished.emit(ok, f"Renamed to '{new_name}'" if ok else f"Rename failed: {msg}")

        threading.Thread(target=worker, daemon=True).start()

    #  File Operations (Pull, Push, Mkdir, Delete) 

    def _download_selected(self) -> None:
        """Download selected files/folders to PC."""
        selected = self._get_selected_items()
        if not selected:
            QMessageBox.information(self, "Download", "Please select one or more items to download.")
            return

        dest_dir = self._dest_dir_input.text().strip()
        if not dest_dir or not os.path.isdir(dest_dir):
            dest_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Destination Folder on PC",
                os.path.expanduser("~/Downloads"),
            )
            if not dest_dir:
                return
            self._dest_dir_input.setText(dest_dir)
            self._config["pc_download_dir"] = dest_dir

        ip, port = self._get_target()
        if not ip:
            return

        self._progress_bar.setVisible(True)
        self._status_lbl.setText("Downloading selected items to PC...")

        def worker():
            success_count = 0
            for item in selected:
                name = item.get("name", "")
                remote_full = os.path.join(self._current_path, name)
                self._sig_progress_status.emit(f"Downloading {name}...")
                ok, msg = adb.pull_from_phone(self._config, remote_full, dest_dir, ip, port)
                if ok:
                    success_count += 1
                else:
                    log.error("Failed to pull %s: %s", remote_full, msg)

            msg = f"Successfully downloaded {success_count}/{len(selected)} items to {dest_dir}"
            self._sig_op_finished.emit(success_count > 0, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _upload_files(self) -> None:
        """Upload one or more PC files to current phone directory."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Upload to Phone")
        if not files:
            return

        ip, port = self._get_target()
        if not ip:
            return

        self._progress_bar.setVisible(True)
        self._status_lbl.setText("Uploading files to phone...")

        def worker():
            success_count = 0
            for local_path in files:
                fname = os.path.basename(local_path)
                self._sig_progress_status.emit(f"Uploading {fname}...")
                ok, msg = adb.push_to_phone(self._config, local_path, self._current_path, ip, port)
                if ok:
                    success_count += 1
                else:
                    log.error("Failed to push %s: %s", fname, msg)

            msg = f"Uploaded {success_count}/{len(files)} files to {self._current_path}"
            self._sig_op_finished.emit(success_count > 0, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _upload_folder(self) -> None:
        """Upload an entire folder intact to phone."""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Upload Intact to Phone")
        if not folder:
            return

        ip, port = self._get_target()
        if not ip:
            return

        folder_name = os.path.basename(folder)
        self._progress_bar.setVisible(True)
        self._status_lbl.setText(f"Uploading folder '{folder_name}' intact...")

        def worker():
            self._sig_progress_status.emit(f"Pushing folder {folder_name}...")
            ok, msg = adb.push_to_phone(self._config, folder, self._current_path, ip, port)
            self._sig_op_finished.emit(ok, f"Folder upload {'completed' if ok else 'failed'}: {msg}")

        threading.Thread(target=worker, daemon=True).start()

    def _create_folder(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        folder_name, ok = QInputDialog.getText(self, "New Folder", "Enter folder name:")
        if not ok or not folder_name.strip():
            return

        folder_name = folder_name.strip().replace(" ", "_")
        target_path = os.path.join(self._current_path, folder_name)

        ip, port = self._get_target()
        if not ip:
            return

        self._progress_bar.setVisible(True)

        def worker():
            ok, msg = adb.mkdir_on_phone(self._config, target_path, ip, port)
            self._sig_op_finished.emit(ok, f"Created folder '{folder_name}'" if ok else f"Failed: {msg}")

        threading.Thread(target=worker, daemon=True).start()

    def _delete_selected(self) -> None:
        selected = self._get_selected_items()
        if not selected:
            return

        names = [item.get("name", "") for item in selected]
        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Are you sure you want to permanently delete {len(selected)} item(s) from phone?\n\n"
            + "\n".join(names[:5]) + ("\n..." if len(names) > 5 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ip, port = self._get_target()
        if not ip:
            return

        self._progress_bar.setVisible(True)

        def worker():
            del_count = 0
            for item in selected:
                name = item.get("name", "")
                remote_full = os.path.join(self._current_path, name)
                ok, _ = adb.delete_on_phone(self._config, remote_full, ip, port)
                if ok:
                    del_count += 1

            self._sig_op_finished.emit(
                del_count > 0,
                f"Deleted {del_count}/{len(selected)} items from phone."
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    def _on_op_finished(self, success: bool, message: str) -> None:
        self._progress_bar.setVisible(False)
        self._status_lbl.setText(message)
        self.refresh()
