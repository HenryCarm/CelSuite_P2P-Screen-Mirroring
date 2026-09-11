"""
Application entry point for ScrcpyUltimateLink.

Sets up logging, config, exception handling, and launches the GUI.
"""

from __future__ import annotations

import sys
import traceback

from src.config import AppConfig
from src.constants import APP_NAME, LOG_FILE
from src.logger import configure as configure_logging, get_logger


def _install_exception_hook() -> None:
    """Install a global exception hook to log unhandled crashes."""
    log = get_logger("crash")

    def hook(exc_type, exc_value, exc_tb):
        log.critical(
            "Unhandled exception:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


def main() -> int:
    """Launch the ScrcpyUltimateLink application."""
    import argparse
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--auto-screenshot", action="store_true", help="Auto screenshot and quit mode")
    parser.add_argument("--screenshot-path", type=str, default="", help="Path to save auto screenshot")
    args, _ = parser.parse_known_args()

    # 1. Load config
    config = AppConfig()

    # 2. Configure logging
    configure_logging(
        log_file=config.get("log_file", LOG_FILE),
        file_logging=config.get("logging_enabled", True),
    )

    # 3. Install crash handler
    _install_exception_hook()

    log = get_logger("app")
    log.info("Starting %s", APP_NAME)

    # 4. Create Qt application
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    import os

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    # Master HD Icon for taskbar, panel, and Alt-Tab
    icon_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icon.png")
    if os.path.exists(icon_file):
        app.setWindowIcon(QIcon(icon_file))

    # 5. Create and show main window
    from src.ui.main_window import MainWindow
    window = MainWindow(config)
    window.show()

    if args.auto_screenshot:
        from PySide6.QtCore import QTimer
        def capture_and_quit():
            target_path = args.screenshot_path or "/home/henry/.gemini/antigravity/brain/755897b6-21b8-41d0-8ad7-f610a2e21dd7/auto_screenshot.png"
            pixmap = window.grab()
            pixmap.save(target_path)
            log.info("Auto screenshot saved to %s", target_path)
            QTimer.singleShot(2000, app.quit)

        log.info("Auto-screenshot mode active: capturing in 5 seconds...")
        QTimer.singleShot(5000, capture_and_quit)

    log.info("GUI ready")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
