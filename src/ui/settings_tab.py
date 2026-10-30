"""
Settings tab for CelStudio Scrcpy Heartbeat.

Provides network, binary path, screenshot directory, and the
CelStudio Liquid Glass & Wallpaper Engine configuration.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig
try:
    from src.constants import (
        APP_DIR,
        DEFAULT_ADB_PORT,
        DEFAULT_DISCOVERY_PORT,
        DEFAULT_HEARTBEAT_PORT,
        DEFAULT_TCP_TRANSFER_PORT,
        DEFAULT_WALLPAPER,
        SCRCPY_HWDECODERS,
        SCRCPY_RENDER_FIT,
    )
except ImportError:  # frozen/stale bundle fallback — never crash at import
    APP_DIR = os.path.dirname(
        os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
    )
    from src.constants import (
        DEFAULT_ADB_PORT,
        DEFAULT_DISCOVERY_PORT,
        DEFAULT_HEARTBEAT_PORT,
        DEFAULT_TCP_TRANSFER_PORT,
        DEFAULT_WALLPAPER,
        SCRCPY_HWDECODERS,
        SCRCPY_RENDER_FIT,
    )
from src.logger import get_logger
from src.ui.animations import AnimatedButton
from src.ui.widgets.section_card import SectionCard

log = get_logger(__name__)

_linux_wp_dir = "/home/henry/Documents/Projects/Python/.png"
def _resolve_wallpapers_dir() -> str:
    if os.path.isdir(_linux_wp_dir):
        return _linux_wp_dir
    try:
        cand = os.path.join(APP_DIR, "wallpapers")
    except NameError:
        cand = ""
    if cand and os.path.isdir(cand):
        return cand
    try:
        if os.path.isdir(APP_DIR):
            return APP_DIR
    except NameError:
        pass
    return _linux_wp_dir


OFFICIAL_WALLPAPERS_DIR = _resolve_wallpapers_dir()


class SettingsTab(QWidget):
    _sig_setup_note = Signal(str)
    """Application settings with grouped configuration sections and CelStudio Theme controls."""

    def __init__(
        self,
        config: AppConfig,
        on_theme_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._on_theme_changed = on_theme_changed
        self._build_ui()
        self._sig_setup_note.connect(self._on_setup_note)

    def _on_setup_note(self, text: str) -> None:
        try:
            self._scrcpy_status_lbl.setText(text)
        except Exception:
            pass

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settings-scroll")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        title = QLabel("CelStudio Settings")
        title.setObjectName("title")
        layout.addWidget(title)

        # 1. CelStudio Liquid Glass & Wallpaper Engine 
        theme_group = SectionCard("CelStudio Theme & Glass Engine")
        theme_layout = QVBoxLayout()
        theme_layout.setSpacing(14)

        # Wallpaper Dropdown & Browse
        wp_label_row = QHBoxLayout()
        wp_label_row.addWidget(QLabel("Background Wallpaper (CelWeave):"))
        theme_layout.addLayout(wp_label_row)

        wp_row = QHBoxLayout()
        self._wp_combo = QComboBox()
        self._populate_wallpapers()
        self._wp_combo.currentIndexChanged.connect(self._on_wallpaper_selected)
        wp_row.addWidget(self._wp_combo, 3)

        wp_browse = AnimatedButton("Browse…")
        wp_browse.clicked.connect(self._browse_wallpaper)
        wp_row.addWidget(wp_browse, 1)
        theme_layout.addLayout(wp_row)

        # Liquid Glass Transparency Slider
        glass_pct = int(float(self._config.get("glass_opacity", 0.65)) * 100)
        self._glass_lbl = QLabel(f"Liquid Glass Opacity: {glass_pct}%")
        self._glass_lbl.setStyleSheet("font-weight: 600;")
        theme_layout.addWidget(self._glass_lbl)

        glass_row = QHBoxLayout()
        self._glass_slider = QSlider(Qt.Orientation.Horizontal)
        self._glass_slider.setRange(15, 100)
        self._glass_slider.setValue(glass_pct)
        self._glass_slider.valueChanged.connect(self._on_glass_changed)
        glass_row.addWidget(self._glass_slider)
        theme_layout.addLayout(glass_row)

        # Dark Overlay Tint Slider
        tint_pct = int(float(self._config.get("wallpaper_tint_opacity", 0.70)) * 100)
        self._tint_lbl = QLabel(f"Wallpaper Dark Tint: {tint_pct}%")
        self._tint_lbl.setStyleSheet("font-weight: 600;")
        theme_layout.addWidget(self._tint_lbl)

        tint_row = QHBoxLayout()
        self._tint_slider = QSlider(Qt.Orientation.Horizontal)
        self._tint_slider.setRange(10, 95)
        self._tint_slider.setValue(tint_pct)
        self._tint_slider.valueChanged.connect(self._on_tint_changed)
        tint_row.addWidget(self._tint_slider)
        theme_layout.addLayout(tint_row)

        theme_group.addLayout(theme_layout)
        layout.addWidget(theme_group)

        # 2. Network Ports 
        ports_group = SectionCard("Network Ports")
        ports_layout = QVBoxLayout()

        self._port_widgets: dict[str, QSpinBox] = {}
        port_defs = [
            ("heartbeat_port", "Heartbeat Port (Phone PC)", DEFAULT_HEARTBEAT_PORT),
            ("discovery_port", "Discovery Port (PC Broadcast)", DEFAULT_DISCOVERY_PORT),
            ("adb_port", "ADB TCP Port", DEFAULT_ADB_PORT),
            ("tcp_transfer_port", "File Transfer TCP Port", DEFAULT_TCP_TRANSFER_PORT),
        ]

        for key, label_text, default in port_defs:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            spin = QSpinBox()
            spin.setRange(1024, 65535)
            spin.setValue(self._config.get(key, default))
            spin.valueChanged.connect(lambda v, k=key: self._save_port(k, v))
            row.addWidget(spin)
            ports_layout.addLayout(row)
            self._port_widgets[key] = spin

        ports_group.addLayout(ports_layout)
        layout.addWidget(ports_group)

        # 3. Binary Paths 
        bins_group = SectionCard("Binary Paths")
        bins_layout = QVBoxLayout()

        # scrcpy
        scrcpy_row = QHBoxLayout()
        scrcpy_row.addWidget(QLabel("scrcpy Binary:"))
        self._scrcpy_input = QLineEdit(self._config.get("scrcpy_bin", "scrcpy"))
        self._scrcpy_input.textChanged.connect(
            lambda t: self._config.__setitem__("scrcpy_bin", t)
        )
        scrcpy_browse = AnimatedButton("Browse…")
        scrcpy_browse.clicked.connect(
            lambda: self._browse_binary(self._scrcpy_input, "scrcpy_bin")
        )
        scrcpy_row.addWidget(self._scrcpy_input)
        scrcpy_row.addWidget(scrcpy_browse)
        bins_layout.addLayout(scrcpy_row)

        # adb
        adb_row = QHBoxLayout()
        adb_row.addWidget(QLabel("ADB Binary:"))
        self._adb_input = QLineEdit(self._config.get("adb_bin", "adb"))
        self._adb_input.textChanged.connect(
            lambda t: self._config.__setitem__("adb_bin", t)
        )
        adb_browse = AnimatedButton("Browse…")
        adb_browse.clicked.connect(
            lambda: self._browse_binary(self._adb_input, "adb_bin")
        )
        adb_row.addWidget(self._adb_input)
        adb_row.addWidget(adb_browse)
        bins_layout.addLayout(adb_row)

        # scrcpy first-run setup (for users without scrcpy installed)
        self._scrcpy_status_lbl = QLabel("Checking scrcpy...")
        self._scrcpy_status_lbl.setWordWrap(True)
        bins_layout.addWidget(self._scrcpy_status_lbl)

        setup_row = QHBoxLayout()
        page_btn = AnimatedButton("Open Download Page")
        page_btn.setToolTip("Open the official scrcpy releases page in your browser")
        page_btn.clicked.connect(self._open_scrcpy_page)
        dl_btn = AnimatedButton("Direct Download")
        dl_btn.setToolTip("Download the correct scrcpy for this PC automatically")
        dl_btn.clicked.connect(self._direct_download_scrcpy)
        up_btn = AnimatedButton("Install Downloaded Archive")
        up_btn.setToolTip("Pick the .zip/.tar.gz you downloaded — we install it for you")
        up_btn.clicked.connect(self._upload_scrcpy_archive)
        setup_row.addWidget(page_btn)
        setup_row.addWidget(dl_btn)
        setup_row.addWidget(up_btn)
        bins_layout.addLayout(setup_row)

        bins_group.addLayout(bins_layout)
        layout.addWidget(bins_group)
        try:
            self._refresh_scrcpy_status()
        except Exception:
            pass

        # 3b. Scrcpy Advanced (v5 command set)
        adv_group = SectionCard("Scrcpy Advanced (v5 command set)")
        adv_layout = QVBoxLayout()

        adv_desc = QLabel("Only non-default values are passed to scrcpy at launch.")
        adv_desc.setWordWrap(True)
        adv_layout.addWidget(adv_desc)

        self._adv_viewonly = QCheckBox("View only (send --no-control)")
        self._adv_viewonly.setChecked(bool(self._config.get("scrcpy_view_only", False)))
        self._adv_viewonly.toggled.connect(lambda v: self._config.__setitem__("scrcpy_view_only", v))
        adv_layout.addWidget(self._adv_viewonly)

        self._adv_gamepad = QCheckBox("Gamepad input (send --gamepad=uhid)")
        self._adv_gamepad.setChecked(bool(self._config.get("scrcpy_gamepad", False)))
        self._adv_gamepad.toggled.connect(lambda v: self._config.__setitem__("scrcpy_gamepad", v))
        adv_layout.addWidget(self._adv_gamepad)

        self._adv_clip = QCheckBox("Clipboard autosync (off sends --no-clipboard-autosync)")
        self._adv_clip.setChecked(bool(self._config.get("scrcpy_clip_autosync", True)))
        self._adv_clip.toggled.connect(lambda v: self._config.__setitem__("scrcpy_clip_autosync", v))
        adv_layout.addWidget(self._adv_clip)

        self._adv_keep = QCheckBox("Keep device active (send --keep-active)")
        self._adv_keep.setChecked(bool(self._config.get("scrcpy_keep_active", False)))
        self._adv_keep.toggled.connect(lambda v: self._config.__setitem__("scrcpy_keep_active", v))
        adv_layout.addWidget(self._adv_keep)

        self._adv_touch = QCheckBox("Show touches (send --show-touches)")
        self._adv_touch.setChecked(bool(self._config.get("scrcpy_show_touches", False)))
        self._adv_touch.toggled.connect(lambda v: self._config.__setitem__("scrcpy_show_touches", v))
        adv_layout.addWidget(self._adv_touch)

        self._adv_top = QCheckBox("Scrcpy window always on top (send --always-on-top)")
        self._adv_top.setChecked(bool(self._config.get("scrcpy_always_on_top", False)))
        self._adv_top.toggled.connect(lambda v: self._config.__setitem__("scrcpy_always_on_top", v))
        adv_layout.addWidget(self._adv_top)

        kb_row = QHBoxLayout()
        kb_row.addWidget(QLabel("Keyboard (--keyboard):"))
        self._adv_kb = QComboBox()
        self._adv_kb.addItems(["sdk", "uhid", "aoa", "disabled"])
        self._adv_kb.setCurrentText(str(self._config.get("scrcpy_keyboard", "sdk")))
        self._adv_kb.currentTextChanged.connect(lambda v: self._config.__setitem__("scrcpy_keyboard", v))
        kb_row.addWidget(self._adv_kb)
        kb_row.addWidget(QLabel("Mouse (--mouse):"))
        self._adv_ms = QComboBox()
        self._adv_ms.addItems(["sdk", "uhid", "aoa", "disabled"])
        self._adv_ms.setCurrentText(str(self._config.get("scrcpy_mouse", "sdk")))
        self._adv_ms.currentTextChanged.connect(lambda v: self._config.__setitem__("scrcpy_mouse", v))
        kb_row.addWidget(self._adv_ms)
        adv_layout.addLayout(kb_row)

        hwdec_row = QHBoxLayout()
        hwdec_row.addWidget(QLabel("Hardware Decoder (--video-decoder):"))
        self._adv_vdec = QComboBox()
        self._adv_vdec.addItems(list(SCRCPY_HWDECODERS))
        self._adv_vdec.setCurrentText(str(self._config.get("scrcpy_video_decoder", "auto")))
        self._adv_vdec.currentTextChanged.connect(lambda v: self._config.__setitem__("scrcpy_video_decoder", v))
        hwdec_row.addWidget(self._adv_vdec)
        hwdec_row.addWidget(QLabel("Render Fit (--render-fit):"))
        self._adv_rfit = QComboBox()
        self._adv_rfit.addItems(list(SCRCPY_RENDER_FIT))
        self._adv_rfit.setCurrentText(str(self._config.get("scrcpy_render_fit", "contain")))
        self._adv_rfit.currentTextChanged.connect(lambda v: self._config.__setitem__("scrcpy_render_fit", v))
        hwdec_row.addWidget(self._adv_rfit)
        adv_layout.addLayout(hwdec_row)

        self._adv_flex = QCheckBox("Flex display (resizable virtual display, send --flex-display)")
        self._adv_flex.setChecked(bool(self._config.get("scrcpy_flex_display", False)))
        self._adv_flex.toggled.connect(lambda v: self._config.__setitem__("scrcpy_flex_display", v))
        adv_layout.addWidget(self._adv_flex)

        self._adv_no_aspect = QCheckBox("Disable aspect ratio lock on resize (send --no-window-aspect-ratio-lock)")
        self._adv_no_aspect.setChecked(bool(self._config.get("scrcpy_no_aspect_ratio_lock", False)))
        self._adv_no_aspect.toggled.connect(lambda v: self._config.__setitem__("scrcpy_no_aspect_ratio_lock", v))
        adv_layout.addWidget(self._adv_no_aspect)

        self._adv_no_vd_dec = QCheckBox("Hide virtual display system decorations (send --no-vd-system-decorations)")
        self._adv_no_vd_dec.setChecked(bool(self._config.get("scrcpy_no_vd_system_decorations", False)))
        self._adv_no_vd_dec.toggled.connect(lambda v: self._config.__setitem__("scrcpy_no_vd_system_decorations", v))
        adv_layout.addWidget(self._adv_no_vd_dec)

        cam_row = QHBoxLayout()
        self._adv_cam_torch = QCheckBox("Camera Torch (--camera-torch)")
        self._adv_cam_torch.setChecked(bool(self._config.get("scrcpy_camera_torch", False)))
        self._adv_cam_torch.toggled.connect(lambda v: self._config.__setitem__("scrcpy_camera_torch", v))
        cam_row.addWidget(self._adv_cam_torch)
        cam_row.addWidget(QLabel("Camera Zoom (--camera-zoom):"))
        self._adv_cam_zoom = QLineEdit(str(self._config.get("scrcpy_camera_zoom", "")))
        self._adv_cam_zoom.setPlaceholderText("e.g. 1.5 (0 = default)")
        self._adv_cam_zoom.textChanged.connect(lambda v: self._config.__setitem__("scrcpy_camera_zoom", v))
        cam_row.addWidget(self._adv_cam_zoom)
        adv_layout.addLayout(cam_row)

        for label_text, key in [
            ("Record to file (--record, empty = off):", "scrcpy_record_path"),
            ("Push target (--push-target):", "scrcpy_push_target"),
            ("Window title (empty = device model):", "scrcpy_window_title"),
            ("Start app on connect (package, empty = off):", "scrcpy_start_app"),
            ("New virtual display WxH (empty = off):", "scrcpy_new_display"),
            ("Background color hex (--background-color, e.g. #1e2327):", "scrcpy_background_color"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            le = QLineEdit(str(self._config.get(key, "")))
            le.textChanged.connect(lambda v, k=key: self._config.__setitem__(k, v))
            row.addWidget(le)
            adv_layout.addLayout(row)

        vb_row = QHBoxLayout()
        vb_row.addWidget(QLabel("Video buffer ms (0 = off):"))
        self._adv_vbuf = QSpinBox()
        self._adv_vbuf.setRange(0, 2000)
        try:
            self._adv_vbuf.setValue(int(self._config.get("scrcpy_video_buffer", 0) or 0))
        except (TypeError, ValueError):
            self._adv_vbuf.setValue(0)
        self._adv_vbuf.valueChanged.connect(lambda v: self._config.__setitem__("scrcpy_video_buffer", v))
        vb_row.addWidget(self._adv_vbuf)
        vb_row.addStretch()
        adv_layout.addLayout(vb_row)

        lst_row = QHBoxLayout()
        for btn_text, flag in [
            ("List Apps", "--list-apps"),
            ("List Displays", "--list-displays"),
            ("List Encoders", "--list-encoders"),
            ("List Cameras", "--list-cameras"),
        ]:
            b = AnimatedButton(btn_text)
            b.clicked.connect(lambda _, f=flag: self._run_scrcpy_list(f))
            lst_row.addWidget(b)
        lst_row.addStretch()
        adv_layout.addLayout(lst_row)

        adv_group.addLayout(adv_layout)
        layout.addWidget(adv_group)

        # 4. Directories 
        dirs_group = SectionCard("Directories")
        dirs_layout = QVBoxLayout()

        ss_row = QHBoxLayout()
        ss_row.addWidget(QLabel("Screenshot Save Directory:"))
        self._ss_dir_input = QLineEdit(
            self._config.get("screenshot_dir", "")
        )
        self._ss_dir_input.setPlaceholderText("~/Pictures/ScrcpyUltimateLink/ (default)")
        self._ss_dir_input.textChanged.connect(
            lambda t: self._config.__setitem__("screenshot_dir", t)
        )
        ss_browse = AnimatedButton("Browse…")
        ss_browse.clicked.connect(self._browse_ss_dir)
        ss_row.addWidget(self._ss_dir_input)
        ss_row.addWidget(ss_browse)
        dirs_layout.addLayout(ss_row)
        dirs_group.addLayout(dirs_layout)
        layout.addWidget(dirs_group)

        # 5. Reset 
        reset_btn = AnimatedButton("Reset All Settings to Defaults")
        reset_btn.setObjectName("action-danger")
        reset_btn.clicked.connect(self._reset_all)
        layout.addWidget(reset_btn)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _populate_wallpapers(self) -> None:
        self._wp_combo.clear()
        current_wp = self._config.get("wallpaper_path", DEFAULT_WALLPAPER)
        
        wallpaper_files = []
        if os.path.exists(OFFICIAL_WALLPAPERS_DIR):
            for ext in ("*.png", "*.jpeg", "*.jpg", "*.webp"):
                wallpaper_files.extend(glob.glob(os.path.join(OFFICIAL_WALLPAPERS_DIR, ext)))

        # Sort so CelWeave wallpapers are on top
        wallpaper_files = sorted(wallpaper_files, key=lambda p: (0 if "CelWeave" in p else 1, os.path.basename(p)))

        selected_idx = 0
        for i, path in enumerate(wallpaper_files):
            name = os.path.splitext(os.path.basename(path))[0]
            self._wp_combo.addItem(name, path)
            if os.path.abspath(path) == os.path.abspath(current_wp):
                selected_idx = i

        # If custom path not in list
        if current_wp and not any(os.path.abspath(p) == os.path.abspath(current_wp) for p in wallpaper_files):
            self._wp_combo.addItem(f"Custom: {os.path.basename(current_wp)}", current_wp)
            selected_idx = self._wp_combo.count() - 1

        self._wp_combo.setCurrentIndex(selected_idx)

    def _on_wallpaper_selected(self, index: int) -> None:
        if index >= 0:
            path = self._wp_combo.itemData(index)
            if path and os.path.exists(path):
                self._config["wallpaper_path"] = path
                if self._on_theme_changed:
                    self._on_theme_changed()

    def _browse_wallpaper(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Wallpaper",
            OFFICIAL_WALLPAPERS_DIR if os.path.exists(OFFICIAL_WALLPAPERS_DIR) else "",
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            self._config["wallpaper_path"] = path
            self._populate_wallpapers()
            if self._on_theme_changed:
                self._on_theme_changed()

    def _on_glass_changed(self, value: int) -> None:
        opacity = round(value / 100.0, 2)
        self._glass_lbl.setText(f"Liquid Glass Opacity: {value}%")
        self._config["glass_opacity"] = opacity
        if self._on_theme_changed:
            self._on_theme_changed()

    def _on_tint_changed(self, value: int) -> None:
        opacity = round(value / 100.0, 2)
        self._tint_lbl.setText(f"Wallpaper Dark Tint: {value}%")
        self._config["wallpaper_tint_opacity"] = opacity
        if self._on_theme_changed:
            self._on_theme_changed()

    def _save_port(self, key: str, value: int) -> None:
        self._config[key] = value
        log.debug("Setting %s = %d", key, value)

    def _browse_binary(self, line_edit: QLineEdit, config_key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {config_key} binary", "",
        )
        if path:
            line_edit.setText(path)
            self._config[config_key] = path

    def _browse_ss_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Screenshot Directory", "",
        )
        if path:
            self._ss_dir_input.setText(path)
            self._config["screenshot_dir"] = path

    def _run_scrcpy_list(self, flag: str) -> None:
        """Run `scrcpy <flag>` and mirror the output into the log panel."""
        from src.networking.adb import find_scrcpy_binary
        scrcpy = find_scrcpy_binary(self._config)
        try:
            kwargs = {"capture_output": True, "text": True, "timeout": 10}
            if sys.platform == "win32":
                import subprocess as _sp
                kwargs["creationflags"] = getattr(_sp, "CREATE_NO_WINDOW", 0x08000000)
            res = subprocess.run([scrcpy, flag], **kwargs)
            out = (res.stdout or res.stderr or "").strip() or "(no output)"
            log.info("scrcpy %s: %s", flag, out)
        except FileNotFoundError:
            log.error("scrcpy binary not found: %s", scrcpy)
        except Exception as exc:
            log.error("scrcpy %s failed: %s", flag, exc)

    def _refresh_scrcpy_status(self) -> None:
        from src import scrcpy_manager as sm
        state, detail = sm.scrcpy_status(self._config)
        if state == "ok":
            self._scrcpy_status_lbl.setText(f"scrcpy ready: {detail}")
        else:
            self._scrcpy_status_lbl.setText(
                f"scrcpy MISSING ({detail}). Use Direct Download or Install Downloaded Archive below."
            )

    def _open_scrcpy_page(self) -> None:
        from src import scrcpy_manager as sm
        if not sm.open_release_page():
            log.error("Could not open the browser — get scrcpy at: %s", sm.SCRCPY_RELEASE_URL if hasattr(sm, "SCRCPY_RELEASE_URL") else "https://github.com/Genymobile/scrcpy/releases")

    def _direct_download_scrcpy(self) -> None:
        import threading
        from src import scrcpy_manager as sm
        self._sig_setup_note.emit("Downloading scrcpy... (see Logs tab)")

        def worker() -> None:
            try:
                def prog(done: int, total: int) -> None:
                    if total > 1:
                        pct = int(done * 100 / total)
                        self._sig_setup_note.emit(f"Downloading scrcpy... {pct}%")
                archive = sm.download_scrcpy(progress_cb=prog)
                scrcpy_bin, _adb_bin = sm.install_archive(archive, self._config)
                try:
                    self._scrcpy_input.setText(scrcpy_bin)
                except Exception:
                    pass
                self._sig_setup_note.emit(f"scrcpy ready: {scrcpy_bin}")
                log.info("scrcpy installed: %s", scrcpy_bin)
            except Exception as exc:
                self._sig_setup_note.emit(f"Download failed: {exc}")
                log.error("scrcpy direct download failed: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    def _upload_scrcpy_archive(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from src import scrcpy_manager as sm
        path, _ = QFileDialog.getOpenFileName(
            self, "Select downloaded scrcpy archive",
            "", "scrcpy archives (*.zip *.tar.gz *.tgz *.tar.xz *.tar)",
        )
        if not path:
            return
        try:
            scrcpy_bin, _adb_bin = sm.install_archive(path, self._config)
            self._scrcpy_input.setText(scrcpy_bin)
            self._refresh_scrcpy_status()
            log.info("scrcpy installed from %s", path)
        except Exception as exc:
            self._sig_setup_note.emit(f"Install failed: {exc}")
            log.error("scrcpy archive install failed: %s", exc)

    def _reset_all(self) -> None:
        self._config.reset()
        for key, spin in self._port_widgets.items():
            spin.setValue(self._config.get(key, 5555))
        self._scrcpy_input.setText(self._config.get("scrcpy_bin", "scrcpy"))
        self._adb_input.setText(self._config.get("adb_bin", "adb"))
        self._ss_dir_input.setText("")
        
        # Reset Theme
        self._populate_wallpapers()
        self._glass_slider.setValue(65)
        self._tint_slider.setValue(70)
        if self._on_theme_changed:
            self._on_theme_changed()
        log.info("Settings reset to defaults")
