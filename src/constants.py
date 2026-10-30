"""
Shared constants for ScrcpyUltimateLink.

All magic numbers, port defaults, timeout values, and protocol
identifiers live here so every module draws from a single source of truth.
"""

from __future__ import annotations

import os
import sys

# ── Application Metadata ──────────────────────────────────────────────────────
APP_NAME = "CelSuite - P2P Screen Mirror"
APP_VERSION = "2610.30.0"
APP_AUTHOR = "Henry"
APP_DOMAIN = "HenryJayZ.CelSuite"

# ── Path Resolution ───────────────────────────────────────────────────────────
# Nuitka onefile extracts to a temp dir, so __file__ is VOLATILE there.
# Invariant: use sys.argv[0]/sys.executable when frozen, __file__ in dev.
def _resolve_app_dir() -> str:
    try:
        if getattr(sys, "frozen", False) or "__compiled__" in globals():
            exe = os.path.abspath(sys.executable or sys.argv[0])
            base = os.path.dirname(exe)
            if "onefile" in exe.lower() or exe.startswith("/tmp/"):
                cwd = os.path.abspath(os.getcwd())
                if os.path.isfile(os.path.join(cwd, "config.json")) or os.path.isdir(os.path.join(cwd, "src")):
                    return cwd
            return base
    except Exception:
        pass
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = _resolve_app_dir()

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
DEFAULT_REVERSE_VIDEO_PORT = 5560  # PC -> Phone video stream UDP
DEFAULT_REVERSE_AUDIO_PORT = 5561  # PC -> Phone audio stream UDP
DEFAULT_REVERSE_INPUT_PORT = 5562  # Phone -> PC input touch/key UDP
DEFAULT_MIRROR_VIDEO_PORT = 5563  # PC -> Phone MJPEG mirror TCP

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

# ── Scrcpy Presets (validated against scrcpy v5.0.1) ─────────────────────────
# NOTE: bare `--tunnel-forward` was REMOVED upstream (needs --tunnel-host;
# superseded by --force-adb-forward). It broke Battery Saver on scrcpy >= 2.1.
SCRCPY_PRESETS: dict[str, list[str]] = {
    "Balanced (Default)": [],
    "High Quality (1080p, 16M)": ["-m", "1920", "-b", "16M"],
    "Fluid (720p, 60fps, 8M)": ["-m", "1280", "--max-fps", "60", "-b", "8M"],
    "Battery Saver (480p, 30fps, 2M)": [
        "-m", "854", "--max-fps", "30", "-b", "2M",
    ],
    "Crisp H.265 (1080p, 60fps, 12M)": [
        "-m", "1920", "--max-fps", "60", "-b", "12M",
        "--video-codec=h265",
    ],
    "Recording (1080p + mkv)": [
        "-m", "1920", "-b", "8M", "--record=celsuite_capture.mkv",
    ],
}

# ── Scrcpy version metadata (https://github.com/Genymobile/scrcpy/releases) ────
SCRCPY_LATEST_KNOWN = "5.0.1"
SCRCPY_MIN_SUPPORTED = "2.0"
SCRCPY_RELEASE_URL = "https://github.com/Genymobile/scrcpy/releases"
SCRCPY_DOWNLOAD_URLS: dict[str, str] = {
    # Verified against the v5.0.1 release assets (mac ships per-arch).
    "windows": "https://github.com/Genymobile/scrcpy/releases/download/v5.0.1/scrcpy-win64-v5.0.1.zip",
    "linux": "https://github.com/Genymobile/scrcpy/releases/download/v5.0.1/scrcpy-linux-x86_64-v5.0.1.tar.gz",
    "macos-arm": "https://github.com/Genymobile/scrcpy/releases/download/v5.0.1/scrcpy-macos-aarch64-v5.0.1.tar.gz",
    "macos-intel": "https://github.com/Genymobile/scrcpy/releases/download/v5.0.1/scrcpy-macos-x86_64-v5.0.1.tar.gz",
}

# Full scrcpy v5 option catalogue (video/audio/control/keyboard/mouse/device
# window/recording/virtual-display/tunnels) — UI + launcher stay in sync.
SCRCPY_VIDEO_CODECS = ("h264", "h265", "av1", "vp8", "vp9")
SCRCPY_AUDIO_SOURCES = (
    "output", "playback", "mic", "mic-unprocessed", "mic-camcorder",
    "mic-voice-recognition", "mic-voice-communication",
    "voice-call", "voice-call-uplink", "voice-call-downlink",
    "voice-performance",
)
SCRCPY_AUDIO_CODECS = ("opus", "aac", "flac", "raw")
SCRCPY_HWDECODERS = ("auto", "disabled", "vaapi", "d3d11va", "videotoolbox")
SCRCPY_RENDER_FIT = ("contain", "cover", "fill", "square-contain", "square-cover", "square-fill")
SCRCPY_KEYBOARDS = ("sdk", "uhid", "aoa", "disabled")
SCRCPY_MICE = ("sdk", "uhid", "aoa", "disabled")

# Flags removed/renamed upstream — stripped from stale presets at launch.
SCRCPY_REMOVED_FLAGS = ("--tunnel-forward",)

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
    # Text badges: emoji render as tofu on systems without color-emoji fonts.
    ".mp4": "[VID]", ".mkv": "[VID]", ".avi": "[VID]",
    ".mov": "[VID]", ".webm": "[VID]",
    ".png": "[IMG]", ".jpg": "[IMG]",
    ".jpeg": "[IMG]", ".webp": "[IMG]",
    ".gif": "[IMG]", ".bmp": "[IMG]",
    ".apk": "[APK]",
    ".mp3": "[AUD]", ".wav": "[AUD]", ".ogg": "[AUD]",
    ".flac": "[AUD]", ".aac": "[AUD]",
    ".pdf": "[DOC]", ".doc": "[DOC]", ".docx": "[DOC]",
    ".txt": "[DOC]", ".rtf": "[DOC]",
    ".zip": "[ZIP]", ".tar": "[ZIP]",
    ".gz": "[ZIP]", ".7z": "[ZIP]",
    ".rar": "[ZIP]",
}

DEFAULT_FILE_ICON = "[FILE]"


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
