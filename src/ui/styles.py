"""
Centralized QSS stylesheet for CelStudio Scrcpy Heartbeat.

Implements the CelStudio Liquid Glass UI standard with translucent
rgba() glassmorphism, glowing emerald green borders, and adjustable opacity.
"""

from __future__ import annotations

# ── Base Palette & Constants ──────────────────────────────────────────────────

COLORS = {
    # Backgrounds — deep emerald obsidian & liquid glass defaults
    "bg_deep": "rgba(6, 12, 8, 0.85)",
    "bg_primary": "transparent",
    "bg_secondary": "transparent",
    "bg_card": "rgba(18, 34, 25, 0.65)",
    "bg_card_hover": "rgba(26, 50, 36, 0.80)",
    "bg_card_glass": "rgba(18, 34, 25, 0.55)",
    "bg_input": "rgba(12, 22, 16, 0.75)",
    "bg_button": "rgba(22, 42, 30, 0.70)",
    "bg_button_hover": "rgba(34, 64, 46, 0.85)",

    # Accents — Cel Emerald / Mint / Neon Sage
    "accent": "#10B981",          # Emerald Green (matching CelWeave Light Green)
    "accent_light": "#34D399",    # Mint Glow
    "accent_indigo": "#059669",   # Deep Emerald
    "accent_glow": "#6EE7B7",     # Bright Neon Mint
    "accent_dim": "#047857",      # Dark Emerald

    # Borders — subtle glowing emerald glass edge
    "border": "rgba(16, 185, 129, 0.30)",
    "border_accent": "#10B981",
    "border_glow": "rgba(52, 211, 153, 0.55)",

    # Text
    "text": "#F0FDF4",
    "text_dim": "#94A3B8",
    "text_on_accent": "#FFFFFF",
    "text_dark": "#061A11",

    # Status
    "success": "#10B981",
    "warning": "#F59E0B",
    "error": "#EF4444",

    # Components
    "tab_inactive": "rgba(14, 26, 19, 0.60)",
    "tab_active": "rgba(24, 48, 34, 0.85)",
    "progress_bg": "rgba(12, 22, 16, 0.80)",
    "progress_fill": "#10B981",
    "scrollbar_bg": "transparent",
    "scrollbar_handle": "rgba(16, 185, 129, 0.40)",
}


def build_stylesheet(glass_opacity: float = 0.33) -> str:
    """
    Generate dynamic CelStudio Emerald Green Liquid Glass QSS stylesheet.
    glass_opacity: float between 0.10 and 1.0 (default: 0.33)
    """
    alpha = max(0.10, min(1.0, glass_opacity))
    card_alpha = round(alpha, 2)
    card_hover_alpha = round(min(1.0, alpha + 0.18), 2)
    input_alpha = round(min(1.0, alpha + 0.12), 2)
    btn_alpha = round(alpha, 2)
    btn_hover_alpha = round(min(1.0, alpha + 0.20), 2)
    sidebar_alpha = round(min(1.0, alpha + 0.15), 2)

    bg_card = f"rgba(16, 32, 22, {card_alpha})"
    bg_card_hover = f"rgba(24, 48, 34, {card_hover_alpha})"
    bg_input = f"rgba(10, 20, 14, {input_alpha})"
    bg_button = f"rgba(20, 38, 28, {btn_alpha})"
    bg_button_hover = f"rgba(32, 60, 44, {btn_hover_alpha})"
    bg_sidebar = f"rgba(8, 16, 11, {sidebar_alpha})"

    return f"""
/* ── CelStudio Emerald Green Liquid Glass Theme ──────────────────────────── */

QMainWindow {{
    background-color: transparent;
}}

QWidget {{
    font-family: "Inter", "Segoe UI", "Roboto", "Noto Sans", sans-serif;
    font-size: 13px;
    color: {COLORS["text"]};
}}

QWidget#central-wallpaper-widget {{
    background-color: transparent;
}}

QWidget#sidebar-container {{
    background-color: {bg_sidebar};
    border-right: 1px solid {COLORS["border"]};
}}

QStackedWidget#content-stack {{
    background-color: transparent;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ── Tab Widget ────────────────────────────────────────────────────────── */

QTabWidget::pane {{
    background-color: transparent;
    border: none;
    border-top: 2px solid {COLORS["border"]};
}}

QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
}}

QTabBar::tab {{
    background: {bg_button};
    color: {COLORS["text_dim"]};
    padding: 10px 24px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 4px;
    font-size: 13px;
    font-weight: 500;
    border: 1px solid {COLORS["border"]};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background: {bg_card_hover};
    color: {COLORS["accent_light"]};
    font-weight: bold;
    border-bottom: 3px solid {COLORS["accent"]};
}}

QTabBar::tab:hover:!selected {{
    background: {bg_button_hover};
    color: {COLORS["text"]};
    border-bottom: 3px solid {COLORS["accent_glow"]};
}}

/* ── Labels ────────────────────────────────────────────────────────────── */

QLabel {{
    color: {COLORS["text"]};
    background: transparent;
}}

QLabel#title {{
    font-size: 24px;
    font-weight: bold;
    color: {COLORS["accent_light"]};
    letter-spacing: 0.5px;
}}

QLabel#status {{
    font-size: 15px;
    font-weight: bold;
    color: {COLORS["success"]};
    padding: 4px 0;
}}

QLabel#status-error {{
    font-size: 15px;
    font-weight: bold;
    color: {COLORS["error"]};
}}

QLabel#status-warning {{
    font-size: 15px;
    font-weight: bold;
    color: {COLORS["warning"]};
}}

QLabel#subtitle {{
    font-size: 14px;
    color: {COLORS["text_dim"]};
}}

QLabel#section-title {{
    font-size: 16px;
    font-weight: bold;
    color: {COLORS["text"]};
    letter-spacing: 0.3px;
    padding-bottom: 2px;
}}

QLabel#stat-value {{
    font-size: 16px;
    font-weight: bold;
    color: {COLORS["text"]};
}}

QLabel#stat-label {{
    font-size: 11px;
    color: {COLORS["text_dim"]};
    text-transform: uppercase;
}}

QLabel#hero-title {{
    font-size: 30px;
    font-weight: bold;
    color: {COLORS["accent_light"]};
}}

/* ── Buttons ───────────────────────────────────────────────────────────── */

QPushButton {{
    background-color: {bg_button};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: bold;
    min-height: 34px;
}}

QPushButton:hover {{
    background-color: {bg_button_hover};
    border-color: {COLORS["border_glow"]};
    color: #FFFFFF;
}}

QPushButton:pressed {{
    background-color: {COLORS["accent_dim"]};
    color: {COLORS["text_on_accent"]};
}}

QPushButton:disabled {{
    background-color: rgba(10, 20, 14, 0.40);
    color: #4A5568;
    border-color: rgba(20, 40, 30, 0.30);
}}

QPushButton#action-primary {{
    background-color: {COLORS["accent"]};
    color: {COLORS["text_on_accent"]};
    border: 1px solid {COLORS["accent_light"]};
    font-size: 14px;
    padding: 10px 24px;
    border-radius: 18px;
    min-height: 40px;
}}

QPushButton#action-primary:hover {{
    background-color: {COLORS["accent_light"]};
    color: {COLORS["text_dark"]};
}}

QPushButton#action-primary:pressed {{
    background-color: {COLORS["accent_dim"]};
    color: #FFFFFF;
}}

QPushButton#action-danger {{
    border-color: {COLORS["error"]};
    color: {COLORS["error"]};
}}

QPushButton#action-danger:hover {{
    background-color: {COLORS["error"]};
    color: {COLORS["text_on_accent"]};
    border-color: {COLORS["error"]};
}}

QPushButton#control-btn {{
    padding: 8px 14px;
    font-size: 12px;
    border-radius: 8px;
    background-color: {bg_card};
    border: 1px solid {COLORS["border"]};
}}

QPushButton#control-btn:hover {{
    background-color: {bg_button_hover};
    border-color: {COLORS["border_glow"]};
}}

QPushButton#control-btn:pressed {{
    background-color: {COLORS["accent"]};
    color: {COLORS["text_on_accent"]};
}}

/* ── Input Widgets ─────────────────────────────────────────────────────── */

QLineEdit, QSpinBox, QComboBox {{
    background-color: {bg_input};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 12px;
    color: {COLORS["text"]};
    font-size: 13px;
    min-height: 22px;
    selection-background-color: {COLORS["accent"]};
    selection-color: {COLORS["text_dark"]};
}}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {COLORS["accent_light"]};
    border-width: 2px;
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: rgba(14, 28, 20, 0.95);
    color: {COLORS["text"]};
    selection-background-color: {COLORS["accent"]};
    selection-color: {COLORS["text_dark"]};
    border: 1px solid {COLORS["border_glow"]};
    border-radius: 8px;
    outline: none;
}}

/* ── Text Edit (Log Panel) ─────────────────────────────────────────────── */

QTextEdit, QPlainTextEdit {{
    background-color: {bg_input};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    padding: 10px;
    color: {COLORS["text"]};
    font-family: "JetBrains Mono", "Cascadia Code", "Fira Code", "Consolas", monospace;
    font-size: 11px;
    selection-background-color: {COLORS["accent"]};
    selection-color: {COLORS["text_dark"]};
}}

/* ── Check Box & Sliders ──────────────────────────────────────────────── */

QCheckBox {{
    color: {COLORS["text"]};
    font-size: 13px;
    spacing: 10px;
}}

QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {COLORS["accent"]};
    border-radius: 5px;
    background: {bg_input};
}}

QCheckBox::indicator:checked {{
    background: {COLORS["accent"]};
    border-color: {COLORS["accent_light"]};
}}

QCheckBox::indicator:hover {{
    border-color: {COLORS["accent_light"]};
}}

QSlider::groove:horizontal {{
    height: 8px;
    background: {bg_input};
    border-radius: 4px;
    border: 1px solid {COLORS["border"]};
}}

QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {COLORS["accent_indigo"]}, stop:1 {COLORS["accent_light"]});
    border-radius: 4px;
}}

QSlider::handle:horizontal {{
    background: #FFFFFF;
    border: 2px solid {COLORS["accent"]};
    width: 18px;
    height: 18px;
    margin: -5px 0;
    border-radius: 9px;
}}

QSlider::handle:horizontal:hover {{
    background: {COLORS["accent_light"]};
    border-color: #FFFFFF;
}}

/* ── Liquid Glass Cards ────────────────────────────────────────────────── */

QFrame#section-card, QFrame#collapsible-card, QFrame#hero-card {{
    background-color: {bg_card};
    border: 1px solid {COLORS["border"]};
    border-radius: 16px;
}}

QFrame#section-card:hover, QFrame#collapsible-card:hover {{
    border-color: {COLORS["border_glow"]};
}}

QFrame#hero-card {{
    background-color: {bg_card};
    border: 1px solid {COLORS["border_accent"]};
    border-radius: 20px;
    padding: 12px;
}}

QPushButton#hero-button {{
    background-color: {COLORS["accent"]};
    color: {COLORS["text_dark"]};
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 14px 28px;
    border-radius: 24px;
    min-height: 48px;
}}

QPushButton#hero-button:hover {{
    background-color: {COLORS["accent_light"]};
}}

QPushButton#collapsible-header {{
    border: none;
    background: transparent;
    text-align: left;
    padding: 4px 0px;
}}

QLabel#collapsible-arrow {{
    color: {COLORS["accent_light"]};
    font-size: 14px;
    font-weight: bold;
}}

QFrame#section-separator {{
    background-color: {COLORS["border"]};
}}

/* ── Stat Card ─────────────────────────────────────────────────────────── */

QFrame#stat-card {{
    background-color: {bg_card};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
    padding: 12px;
}}

QFrame#stat-card:hover {{
    background-color: {bg_card_hover};
    border-color: {COLORS["border_glow"]};
}}

QFrame#stat-card-glow {{
    background-color: {bg_card_hover};
    border: 1px solid {COLORS["accent_light"]};
    border-radius: 12px;
    padding: 12px;
}}

/* ── Progress Bar ──────────────────────────────────────────────────────── */

QProgressBar {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    text-align: center;
    color: {COLORS["text_dark"]};
    font-weight: bold;
    height: 24px;
    background-color: {bg_input};
    font-size: 11px;
}}

QProgressBar::chunk {{
    background-color: {COLORS["accent"]};
    border-radius: 7px;
}}

/* ── Sidebar & List Widget ─────────────────────────────────────────────── */

QListWidget {{
    background-color: {bg_input};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    font-size: 14px;
    outline: none;
    padding: 8px;
}}

QListWidget#sidebar {{
    background-color: transparent;
    border: none;
}}

QListWidget#sidebar::item {{
    padding: 12px 14px;
    border-radius: 10px;
    margin: 3px 6px;
    font-weight: 600;
    color: {COLORS["text_dim"]};
}}

QListWidget#sidebar::item:selected {{
    background-color: {COLORS["accent"]};
    color: {COLORS["text_dark"]};
    border: 1px solid {COLORS["accent_light"]};
    font-weight: bold;
}}

QListWidget#sidebar::item:hover:!selected {{
    background-color: {bg_button};
    color: {COLORS["text"]};
}}

/* ── Scrollbars ────────────────────────────────────────────────────────── */

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: rgba(16, 185, 129, 0.35);
    border-radius: 4px;
    min-height: 36px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS["accent_light"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    border-radius: 4px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: rgba(16, 185, 129, 0.35);
    border-radius: 4px;
    min-width: 36px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLORS["accent_light"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Tooltips & Drop Zone ──────────────────────────────────────────────── */

QToolTip {{
    background-color: rgba(12, 24, 18, 0.95);
    color: {COLORS["text"]};
    border: 1px solid {COLORS["accent_light"]};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

QFrame#drop-zone {{
    border: 2px dashed {COLORS["accent_glow"]};
    border-radius: 14px;
    background-color: {bg_card};
}}

QFrame#drop-zone-active {{
    border: 2px solid {COLORS["accent_light"]};
    background-color: {bg_button_hover};
    border-radius: 14px;
}}
"""


STYLESHEET = build_stylesheet(0.65)
