"""
Shared constants for ScrcpyUltimateLink.

All magic numbers, port defaults, timeout values, and protocol
identifiers live here so every module draws from a single source of truth.
"""

from __future__ import annotations

import os
import sys

# ── Application Metadata ──────────────────────────────────────────────────────
APP_NAME = "CelSuite - Scrcpy Heartbeat"
APP_VERSION = "269.3.1"
APP_AUTHOR = "Henry"
APP_DOMAIN = "HenryJayZ.CelSuite"

# ── Path Resolution ───────────────────────────────────────────────────────────
# When frozen (Nuitka / PyInstaller), sys.argv[0] points to the binary.
# During development, it points to main.py — either way we want the directory
# that contains the executable so config/logs stay next to the binary.
# Use __file__ for both dev and Nuitka (which extracts data to a temp dir in onefile)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── CelStudio Assets ─────────────────────────────────────────────────────────
_local_wp = os.path.join(APP_DIR, "wallpaper.jpg")
_linux_wp = "/home/henry/Documents/Projects/Python/.png/CelWeave Light Green.jpeg"
DEFAULT_WALLPAPER = _linux_wp if os.path.exists(_linux_wp) else _local_wp

_local_icon = os.path.join(APP_DIR, "icon.png")
_linux_icon = "/home/henry/Documents/Projects/Python/Scrcpy Heartbeat/icon.png"
DEFAULT_ICON = _linux_icon if os.path.exists(_linux_icon) else _local_icon

CONFIG_FILENAME = "config.json"
LOG_FILENAME = "ScrcpyHeartbeat.log"

# CONFIG_DIR needs to be where the executable is so settings persist.
# Nuitka onefile extracts to a temp dir, so APP_DIR is volatile.
if getattr(sys, "frozen", False):
    CONFIG_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    CONFIG_DIR = APP_DIR

CONFIG_FILE = os.path.join(CONFIG_DIR, CONFIG_FILENAME)
LOG_FILE = os.path.join(CONFIG_DIR, LOG_FILENAME)

# ── Network Defaults ──────────────────────────────────────────────────────────
DEFAULT_HEARTBEAT_PORT = 5556   # Phone → PC heartbeat UDP
DEFAULT_DISCOVERY_PORT = 5557   # PC → Phone discovery broadcast UDP
DEFAULT_ADB_PORT = 5555         # ADB TCP port on phone
DEFAULT_TCP_TRANSFER_PORT = 5558  # Bi-directional file transfer TCP

HEARTBEAT_INTERVAL_SEC = 4.0    # How often the phone sends heartbeats
DISCOVERY_INTERVAL_SEC = 3.0    # How often the PC broadcasts discovery
DASHBOARD_REFRESH_SEC = 5.0     # Hardware dashboard polling interval
HEARTBEAT_DEBOUNCE_SEC = 3.0    # Minimum gap between handling heartbeats

# ── Network Timeouts ──────────────────────────────────────────────────────────
UDP_LISTEN_TIMEOUT_SEC = 2.0
ADB_COMMAND_TIMEOUT_SEC = 5
ADB_CONNECT_TIMEOUT_SEC = 5
SUBNET_SCAN_TIMEOUT_SEC = 0.5
FILE_TRANSFER_TIMEOUT_SEC = 15
LATENCY_TEST_TIMEOUT_SEC = 1.5
LATENCY_TEST_ROUNDS = 3

# ── File Transfer ─────────────────────────────────────────────────────────────
TRANSFER_CHUNK_SIZE = 262_144   # 256 KB chunks for TCP file transfer
PROGRESS_UPDATE_INTERVAL_SEC = 0.5
MAX_FILENAME_LENGTH = 255
LARGE_FILE_THRESHOLD = 200 * 1024 * 1024  # 200 MB

# ── Subnet Scanner ────────────────────────────────────────────────────────────
SCANNER_MAX_WORKERS = 50
SCANNER_PORT_RANGE = [5555, 5556, 5557, 5558]

# ── Protocol Messages ─────────────────────────────────────────────────────────
# Heartbeat / Discovery
PROTO_HEARTBEAT_PREFIX = "HELLO_"
PROTO_DISCOVERY_PREFIX = "SCRCPC_HERE"
PROTO_CLIPBOARD_PREFIX = "HELLO_CLIPBOARD"

# File transfer headers
PROTO_FILE_SEND = "FILE_SEND"
PROTO_FILE_LIST = "FILE_LIST"
PROTO_FILE_GET = "FILE_GET"
PROTO_FILE_CANCEL = "FILE_CANCEL"
PROTO_FILE_ACK = "FILE_ACK"
PROTO_SEPARATOR = "|"
PROTO_VERSION = 1

# ── Scrcpy Presets ────────────────────────────────────────────────────────────
SCRCPY_PRESETS: dict[str, list[str]] = {
    "Balanced (Default)": [],
    "High Quality (1080p, 16M)": ["-m", "1920", "-b", "16M"],
    "Fluid (720p, 60fps, 8M)": ["-m", "1280", "--max-fps", "60", "-b", "8M"],
    "Battery Saver (480p, 30fps, 2M)": [
        "-m", "854", "--max-fps", "30", "-b", "2M", "--tunnel-forward",
    ],
}

# ── Connection States ─────────────────────────────────────────────────────────
class ConnectionState:
    """Enum-like connection state constants."""
    DISCONNECTED = "disconnected"
    DISCOVERING = "discovering"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    MIRRORING = "mirroring"
    ERROR = "error"

# ── Android Keycode Map (common remotes) ──────────────────────────────────────
KEYCODE_POWER = 26
KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_RECENTS = 187
KEYCODE_VOLUME_UP = 24
KEYCODE_VOLUME_DOWN = 25
KEYCODE_SCREEN_OFF = 223
KEYCODE_MEDIA_PLAY_PAUSE = 85
KEYCODE_MEDIA_NEXT = 87
KEYCODE_MEDIA_PREVIOUS = 88

# ── File Type Icons (for GUI) ─────────────────────────────────────────────────
FILE_TYPE_ICONS: dict[str, str] = {
    ".mp4": "\U0001f3a5", ".mkv": "\U0001f3a5", ".avi": "\U0001f3a5",
    ".mov": "\U0001f3a5", ".webm": "\U0001f3a5",
    ".png": "\U0001f5bc\ufe0f", ".jpg": "\U0001f5bc\ufe0f",
    ".jpeg": "\U0001f5bc\ufe0f", ".webp": "\U0001f5bc\ufe0f",
    ".gif": "\U0001f5bc\ufe0f", ".bmp": "\U0001f5bc\ufe0f",
    ".apk": "\U0001f4e6",
    ".mp3": "\U0001f3b5", ".wav": "\U0001f3b5", ".ogg": "\U0001f3b5",
    ".flac": "\U0001f3b5", ".aac": "\U0001f3b5",
    ".pdf": "\U0001f4c4", ".doc": "\U0001f4c4", ".docx": "\U0001f4c4",
    ".txt": "\U0001f4c4", ".rtf": "\U0001f4c4",
    ".zip": "\U0001f5dc\ufe0f", ".tar": "\U0001f5dc\ufe0f",
    ".gz": "\U0001f5dc\ufe0f", ".7z": "\U0001f5dc\ufe0f",
    ".rar": "\U0001f5dc\ufe0f",
}

DEFAULT_FILE_ICON = "\U0001f4c1"


def get_file_icon(filename: str) -> str:
    """Return an emoji icon for a file based on its extension."""
    ext = os.path.splitext(filename)[1].lower()
    return FILE_TYPE_ICONS.get(ext, DEFAULT_FILE_ICON)


def format_size(size_bytes: int) -> str:
    """Format byte count into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
