"""
Unified configuration manager for ScrcpyUltimateLink.

Provides a single ``AppConfig`` class that all modules share.  Config is
loaded once at startup, mutated through setter helpers (which auto-save),
and persisted atomically to ``config.json`` next to the executable.

Thread Safety
-------------
All reads and writes are protected by a ``threading.Lock``.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from typing import Any

from src.constants import (
    APP_DIR,
    CONFIG_FILE,
    DEFAULT_ADB_PORT,
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_HEARTBEAT_PORT,
    DEFAULT_TCP_TRANSFER_PORT,
    LOG_FILE,
)

# Schema version — bump when adding/removing keys so we can migrate
_SCHEMA_VERSION = 2

_DEFAULTS: dict[str, Any] = {
    "schema_version": _SCHEMA_VERSION,
    # Network
    "heartbeat_port": DEFAULT_HEARTBEAT_PORT,
    "discovery_port": DEFAULT_DISCOVERY_PORT,
    "adb_port": DEFAULT_ADB_PORT,
    "tcp_transfer_port": DEFAULT_TCP_TRANSFER_PORT,
    # Binaries
    "scrcpy_bin": "scrcpy",
    "adb_bin": "adb",
    # Paths
    "log_file": LOG_FILE,
    "screenshot_dir": "",  # Empty = use ~/Pictures/ScrcpyUltimateLink/
    # Features
    "logging_enabled": True,
    "scrcpy_preset": "Balanced (Default)",
    "auto_clip_sync": False,
    # CelStudio Liquid Glass & Wallpaper Engine
    "wallpaper_path": "/home/henry/Documents/Projects/Python/.png/CelWeave Light Green.jpeg",
    "glass_opacity": 0.33,
    "wallpaper_tint_opacity": 0.33,
    # Saved state
    "last_phone_ip": "",
    "last_phone_port": DEFAULT_ADB_PORT,
    # Window
    "window_width": 950,
    "window_height": 720,
    "window_x": -1,
    "window_y": -1,
}


class AppConfig:
    """
    Thread-safe, auto-persisting application configuration.

    Usage::

        cfg = AppConfig()          # loads or creates config.json
        port = cfg["adb_port"]     # read
        cfg["adb_port"] = 5556     # write + auto-save
        cfg.save()                 # explicit save (usually not needed)
    """

    def __init__(self, path: str = CONFIG_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._load()

    # ── Public API ────────────────────────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        """Return config value, falling back to *default*."""
        with self._lock:
            return self._data.get(key, default)

    def update(self, mapping: dict[str, Any]) -> None:
        """Bulk-update multiple keys and save once."""
        with self._lock:
            self._data.update(mapping)
        self.save()

    def reset(self) -> None:
        """Reset all settings to defaults and save."""
        with self._lock:
            self._data = dict(_DEFAULTS)
        self.save()

    @property
    def data(self) -> dict[str, Any]:
        """Return a snapshot copy of the full config dict."""
        with self._lock:
            return dict(self._data)

    # ── Path Helpers ──────────────────────────────────────────────────────

    def screenshot_directory(self) -> str:
        """Return the configured screenshot directory, creating it if needed."""
        d = self.get("screenshot_dir", "")
        if not d:
            d = os.path.join(os.path.expanduser("~"), "Pictures", "ScrcpyUltimateLink")
        os.makedirs(d, exist_ok=True)
        return d

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self) -> None:
        """Atomically write config to disk."""
        with self._lock:
            snapshot = dict(self._data)
        try:
            dir_name = os.path.dirname(self._path)
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp", prefix="config_", dir=dir_name or ".",
            )
            with os.fdopen(fd, "w") as f:
                json.dump(snapshot, f, indent=2)
            os.replace(tmp_path, self._path)
        except OSError:
            # If atomic write fails, fall back to direct write
            try:
                with open(self._path, "w") as f:
                    json.dump(snapshot, f, indent=2)
            except OSError:
                pass

    def _load(self) -> None:
        """Load config from disk, merging with defaults for missing keys."""
        loaded: dict[str, Any] = {}
        try:
            if os.path.exists(self._path):
                with open(self._path, "r") as f:
                    loaded = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

        # Start from defaults, overlay with loaded values
        merged = dict(_DEFAULTS)
        for key, value in loaded.items():
            if key in merged:
                merged[key] = value

        # Migrate schema if needed
        old_version = loaded.get("schema_version", 1)
        if old_version < _SCHEMA_VERSION:
            merged = self._migrate(merged, old_version)

        with self._lock:
            self._data = merged

        # Persist merged config (adds any new default keys)
        if merged != loaded:
            self.save()

    @staticmethod
    def _migrate(data: dict[str, Any], from_version: int) -> dict[str, Any]:
        """Run incremental migrations from *from_version* to current."""
        if from_version < 2:
            # v1 → v2: rename "connection_mode" (removed), add tcp_transfer_port
            data.pop("connection_mode", None)
            data.pop("app_version", None)
            data.pop("last_ip_file", None)
            data.setdefault("tcp_transfer_port", DEFAULT_TCP_TRANSFER_PORT)
            data.setdefault("adb_bin", "adb")
            data.setdefault("screenshot_dir", "")
            data.setdefault("last_phone_ip", "")
            data.setdefault("last_phone_port", DEFAULT_ADB_PORT)
            data["schema_version"] = 2
        return data

    def __repr__(self) -> str:
        return f"AppConfig({self._path!r})"
