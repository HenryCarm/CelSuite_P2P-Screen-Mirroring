"""
scrcpy first-run setup for CelSuite.

Covers users who don't have scrcpy installed:
  1. "Open Download Page" — opens the GitHub releases page in a browser.
  2. "Direct Download"    — downloads the right asset for this OS (resolved
     live via the GitHub API, with static fallback URLs), with progress.
  3. "Install Downloaded Archive" — user picks the .zip/.tar.gz they grabbed
     themselves; we extract it, find scrcpy (+adb), install into the app
     tools dir and point the config at it.

No new third-party dependencies: download uses `requests` when available,
otherwise stdlib `urllib`.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from typing import Callable, Optional

from src.config import AppConfig
from src.constants import (
    CONFIG_DIR,
    SCRCPY_DOWNLOAD_URLS,
    SCRCPY_LATEST_KNOWN,
    SCRCPY_RELEASE_URL,
)
from src.logger import get_logger
from src.networking.adb import find_adb_binary, find_scrcpy_binary

log = get_logger(__name__)

TOOLS_DIR = os.path.join(CONFIG_DIR, "tools")


def _platform_key() -> str:
    plat = sys.platform
    if plat == "win32":
        return "windows"
    if plat == "darwin":
        machine = platform.machine().lower()
        return "macos-arm" if "arm" in machine else "macos-intel"
    return "linux"


def scrcpy_status(config: AppConfig) -> tuple[str, str]:
    """Return ("ok"|"missing"|"outdated", detail string)."""
    from src.networking.adb import get_scrcpy_version, is_scrcpy_compatible

    binary = find_scrcpy_binary(config)
    if binary in ("scrcpy", "scrcpy.exe") and shutil.which(binary) is None:
        if os.path.isfile(os.path.join(TOOLS_DIR, "scrcpy")) or os.path.isfile(
            os.path.join(TOOLS_DIR, "scrcpy.exe")
        ):
            pass
        else:
            return "missing", "scrcpy not found on PATH or in app tools"
    ok, ver = is_scrcpy_compatible(config)
    if not ok:
        return "missing", ver
    return "ok", ver


def resolve_download_url() -> tuple[str, str]:
    """Resolve (url, filename) for this OS, live via API with static fallback."""
    key = _platform_key()
    wants = {
        "windows": "win64",
        "linux": "linux-x86_64",
        "macos-arm": "macos-aarch64",
        "macos-intel": "macos-x86_64",
    }.get(key, "linux-x86_64")
    # Live resolution (tiny JSON, works for future versions too).
    try:
        try:
            import requests

            resp = requests.get(
                "https://api.github.com/repos/Genymobile/scrcpy/releases/latest",
                timeout=15,
            )
            data = resp.json()
        except ImportError:
            import json
            import urllib.request

            with urllib.request.urlopen(
                "https://api.github.com/repos/Genymobile/scrcpy/releases/latest",
                timeout=15,
            ) as r:
                data = json.load(r)
        for asset in data.get("assets", []):
            name = str(asset.get("name", ""))
            if wants in name and (name.endswith(".zip") or name.endswith(".tar.gz")):
                url = asset.get("browser_download_url", "")
                if url:
                    log.info("Resolved scrcpy asset via API: %s", name)
                    return url, name
    except Exception as exc:
        log.warning("GitHub API resolution failed, using fallback: %s", exc)
    url = SCRCPY_DOWNLOAD_URLS.get(key, SCRCPY_DOWNLOAD_URLS["linux"])
    return url, url.rsplit("/", 1)[-1]


def download_scrcpy(
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Download the scrcpy asset into a temp file. Returns the file path."""
    url, filename = resolve_download_url()
    log.info("Downloading scrcpy %s ...", filename)
    tmp = os.path.join(tempfile.gettempdir(), filename)

    def _report(done: int, total: int) -> None:
        if progress_cb:
            try:
                progress_cb(done, total)
            except Exception:
                pass

    try:
        import requests

        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0) or 0)
            done = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=262_144):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    _report(done, total)
    except ImportError:
        import urllib.request

        def _hook(blocks: int, block_size: int, total: int) -> None:
            _report(blocks * block_size, total or 0)

        urllib.request.urlretrieve(url, tmp, reporthook=_hook)
    _report(1, 1)
    log.info("scrcpy downloaded to %s", tmp)
    return tmp


def install_archive(archive_path: str, config: AppConfig) -> tuple[str, str]:
    """Extract a user-supplied (or downloaded) scrcpy archive and wire config.

    Returns (scrcpy_bin, adb_bin). Raises on failure.
    """
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Archive not found: {archive_path}")
    lower = archive_path.lower()
    if lower.endswith(".zip"):
        kind = "zip"
    elif lower.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar")):
        kind = "tar"
    else:
        raise ValueError("Unsupported archive — use the .zip (Windows) or .tar.gz (Linux/macOS) from the scrcpy release page")

    dest = os.path.join(TOOLS_DIR, "scrcpy-pkg")
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(dest)
    else:
        with tarfile.open(archive_path) as tf:
            tf.extractall(dest)

    exe = "scrcpy.exe" if sys.platform == "win32" else "scrcpy"
    adb_exe = "adb.exe" if sys.platform == "win32" else "adb"
    found_scrcpy = found_adb = ""
    for root, _dirs, files in os.walk(dest):
        if exe in files and not found_scrcpy:
            found_scrcpy = os.path.join(root, exe)
        if adb_exe in files and not found_adb:
            found_adb = os.path.join(root, adb_exe)
    if not found_scrcpy:
        raise FileNotFoundError(
            f"No {exe} inside {os.path.basename(archive_path)} — did you download the full scrcpy release asset?"
        )
    for path in (found_scrcpy, found_adb):
        if path and os.path.isfile(path) and sys.platform != "win32":
            mode = os.stat(path).st_mode
            os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    config.update({"scrcpy_bin": found_scrcpy})
    if found_adb:
        config.update({"adb_bin": found_adb})
    log.info("Installed scrcpy: %s (adb: %s)", found_scrcpy, found_adb or "system")
    return found_scrcpy, found_adb or find_adb_binary(config)


def open_release_page() -> bool:
    """Open the scrcpy download page in the default browser."""
    try:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        opened = QDesktopServices.openUrl(QUrl(SCRCPY_RELEASE_URL))
        log.info("Opened scrcpy release page (v%s+): %s", SCRCPY_LATEST_KNOWN, SCRCPY_RELEASE_URL)
        return bool(opened)
    except Exception as exc:
        log.error("Could not open browser: %s", exc)
        return False
