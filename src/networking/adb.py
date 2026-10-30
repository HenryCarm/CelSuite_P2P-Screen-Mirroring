"""
ADB command wrappers for ScrcpyUltimateLink.

Every ADB interaction flows through this module so we get consistent
error handling, timeout management, and logging.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any, Optional

from src.config import AppConfig
from src.constants import (
    ADB_COMMAND_TIMEOUT_SEC,
    ADB_CONNECT_TIMEOUT_SEC,
    DEFAULT_ADB_PORT,
)
from src.logger import get_logger

log = get_logger(__name__)

# ── Device Cache ──────────────────────────────────────────────────────────────
# ADB devices results are cached for a short period to avoid hammering the ADB
# server on every heartbeat + dashboard refresh cycle.

_device_cache: list[dict[str, str]] = []
_device_cache_time: float = 0.0
_device_cache_ttl: float = 2.0  # seconds
_device_cache_lock = threading.Lock()


import sys

# Windows process creation flags to suppress black console popup windows
_SUBPROCESS_FLAGS: dict[str, Any] = {}
if sys.platform == "win32":
    _SUBPROCESS_FLAGS["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess command with Windows CREATE_NO_WINDOW flags."""
    opts = dict(_SUBPROCESS_FLAGS)
    opts.update(kwargs)
    return subprocess.run(cmd, **opts)


def _clear_device_cache() -> None:
    """Invalidate the device cache."""
    global _device_cache_time
    with _device_cache_lock:
        _device_cache_time = 0.0


# ── Binary Detection ──────────────────────────────────────────────────────────

def find_adb_binary(config: AppConfig) -> str:
    """Return the path to the ADB binary, checking config, APP_DIR, PATH, and Windows paths."""
    configured = config.get("adb_bin", "adb")
    if configured and configured != "adb" and shutil.which(configured):
        return configured

    # 1. Check next to executable / APP_DIR (for portable Windows releases)
    from src.constants import APP_DIR
    for name in ("adb.exe", "adb"):
        local_bin = os.path.join(APP_DIR, name)
        if os.path.isfile(local_bin):
            return local_bin

    # 2. Check system PATH
    found = shutil.which("adb") or shutil.which("adb.exe")
    if found:
        return found

    # 3. Check common Windows install directories
    if sys.platform == "win32":
        win_candidates = [
            r"C:\platform-tools\adb.exe",
            r"C:\scrcpy\adb.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Android\platform-tools\adb.exe"),
        ]
        for path in win_candidates:
            if os.path.isfile(path):
                return path

    return "adb"


def find_scrcpy_binary(config: AppConfig) -> str:
    """Return the path to the scrcpy binary, checking config, APP_DIR, PATH, and Windows paths."""
    configured = config.get("scrcpy_bin", "scrcpy")
    if configured and configured != "scrcpy" and shutil.which(configured):
        return configured

    # 1. Check next to executable / APP_DIR
    from src.constants import APP_DIR
    for name in ("scrcpy.exe", "scrcpy"):
        local_bin = os.path.join(APP_DIR, name)
        if os.path.isfile(local_bin):
            return local_bin

    # 2. Check system PATH
    found = shutil.which("scrcpy") or shutil.which("scrcpy.exe")
    if found:
        return found

    # 3. Check common Windows install directories
    if sys.platform == "win32":
        win_candidates = [
            r"C:\scrcpy\scrcpy.exe",
            r"C:\Program Files\scrcpy\scrcpy.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\scrcpy\scrcpy.exe"),
        ]
        for path in win_candidates:
            if os.path.isfile(path):
                return path

    return "scrcpy"


def get_scrcpy_version(config: AppConfig) -> str:
    """Return `scrcpy --version` output, or an error message."""
    scrcpy = find_scrcpy_binary(config)
    try:
        result = _run(
            [scrcpy, "--version"],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        out = (result.stdout or result.stderr or "").strip().split("\n")
        return out[0] if out and out[0] else "scrcpy version unknown"
    except FileNotFoundError:
        return "scrcpy not found"
    except subprocess.SubprocessError as exc:
        return f"scrcpy error: {exc}"


def is_scrcpy_compatible(config: AppConfig) -> tuple[bool, str]:
    """Check scrcpy meets SCRCPY_MIN_SUPPORTED (best-effort parse)."""
    from src.constants import SCRCPY_MIN_SUPPORTED
    ver = get_scrcpy_version(config)
    import re
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", ver)
    if not m:
        return False, ver
    try:
        major = int(m.group(1))
        min_major = int(str(SCRCPY_MIN_SUPPORTED).split(".")[0])
        if major < min_major:
            return False, ver
    except ValueError:
        return False, ver
    return True, ver


def rename_on_phone(
    config: AppConfig,
    old_remote: str,
    new_remote: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Rename/move a file on the phone via `mv` (used by Phone Explorer)."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"
    try:
        result = _run(
            [adb, "-s", target, "shell", "mv", old_remote, new_remote],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        if result.returncode == 0:
            return True, f"Renamed to {new_remote}"
        return False, (result.stderr or result.stdout or "rename failed").strip()
    except subprocess.SubprocessError as exc:
        return False, str(exc)


def build_scrcpy_args(config: AppConfig, preset_extra: Optional[list[str]] = None) -> list[str]:
    """Merge preset + Mirror-tab quick row + Settings advanced flags.

    Only non-default values are emitted, keeping the command compatible
    with scrcpy >= 2.0 (see constants SCRCPY_* catalogue, audited vs v5.0.1).
    """
    from src.constants import SCRCPY_REMOVED_FLAGS
    args: list[str] = []
    for a in (preset_extra or []):
        if a in SCRCPY_REMOVED_FLAGS:
            log.warning("Dropping removed scrcpy flag from preset: %s", a)
            continue
        args.append(a)
    codec = str(config.get("scrcpy_codec", "h264") or "h264")
    if codec != "h264":
        args.append("--video-codec=" + codec)
    asrc = str(config.get("scrcpy_audio_source", "playback") or "playback")
    if config.get("scrcpy_no_audio", False):
        args.append("--no-audio")
    elif asrc != "playback":
        args.append("--audio-source=" + asrc)
    if config.get("scrcpy_view_only", False):
        args.append("--no-control")
    if config.get("scrcpy_fullscreen", False):
        args.append("--fullscreen")
    if config.get("scrcpy_turn_screen_off", False):
        args.append("--turn-screen-off")
    if config.get("scrcpy_stay_awake", False):
        args.append("--stay-awake")
    if config.get("scrcpy_keep_active", False):
        args.append("--keep-active")
    if config.get("scrcpy_show_touches", False):
        args.append("--show-touches")
    if config.get("scrcpy_always_on_top", False):
        args.append("--always-on-top")
    kb = str(config.get("scrcpy_keyboard", "sdk") or "sdk")
    if kb != "sdk":
        args.append("--keyboard=" + kb)
    ms = str(config.get("scrcpy_mouse", "sdk") or "sdk")
    if ms != "sdk":
        args.append("--mouse=" + ms)
    if config.get("scrcpy_gamepad", False):
        args.append("--gamepad=uhid")
    if not config.get("scrcpy_clip_autosync", True):
        args.append("--no-clipboard-autosync")
    rec = str(config.get("scrcpy_record_path", "") or "").strip()
    if rec:
        args.append("--record=" + rec)
    pt = str(config.get("scrcpy_push_target", "") or "").strip()
    if pt:
        args.append("--push-target=" + pt)
    wt = str(config.get("scrcpy_window_title", "") or "").strip()
    if wt:
        args.append("--window-title=" + wt)
    sa = str(config.get("scrcpy_start_app", "") or "").strip()
    if sa:
        args.append("--start-app=" + sa)
    nd = str(config.get("scrcpy_new_display", "") or "").strip()
    if nd:
        args.append("--new-display=" + nd)
    try:
        vb = int(config.get("scrcpy_video_buffer", 0) or 0)
    except (TypeError, ValueError):
        vb = 0
    if vb > 0:
        args.append(f"--video-buffer={vb}")

    # scrcpy v5.0 / v5.0.1 flags
    vdec = str(config.get("scrcpy_video_decoder", "auto") or "auto").strip()
    if vdec and vdec != "auto":
        args.append("--video-decoder=" + vdec)
    if config.get("scrcpy_flex_display", False):
        args.append("--flex-display")
    if config.get("scrcpy_no_aspect_ratio_lock", False):
        args.append("--no-window-aspect-ratio-lock")
    if config.get("scrcpy_no_vd_system_decorations", False):
        args.append("--no-vd-system-decorations")
    rfit = str(config.get("scrcpy_render_fit", "contain") or "contain").strip()
    if rfit and rfit != "contain":
        args.append("--render-fit=" + rfit)
    if config.get("scrcpy_camera_torch", False):
        args.append("--camera-torch")
    try:
        czoom = float(config.get("scrcpy_camera_zoom", 0.0) or 0.0)
        if czoom > 0:
            args.append(f"--camera-zoom={czoom}")
    except (TypeError, ValueError):
        pass
    bgcolor = str(config.get("scrcpy_background_color", "") or "").strip()
    if bgcolor:
        args.append("--background-color=" + bgcolor)
    return args


def is_adb_available(config: AppConfig) -> bool:
    """Check if ADB is reachable."""
    adb = find_adb_binary(config)
    try:
        result = _run(
            [adb, "version"],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_adb_version(config: AppConfig) -> str:
    """Return the ADB version string, or an error message."""
    adb = find_adb_binary(config)
    try:
        result = _run(
            [adb, "version"],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        if result.returncode == 0:
            first_line = result.stdout.strip().split("\n")[0]
            return first_line
        return f"ADB error: {result.stderr.strip()}"
    except FileNotFoundError:
        return "ADB not found"
    except subprocess.SubprocessError as exc:
        return f"ADB error: {exc}"


# ── Device Listing ────────────────────────────────────────────────────────────

def get_adb_devices(config: AppConfig) -> list[dict[str, str]]:
    """
    Return a list of connected ADB devices.

    Each entry is ``{"serial": "ip:port", "status": "device"}``.
    Results are cached for 2 seconds to reduce subprocess overhead.
    """
    global _device_cache, _device_cache_time

    with _device_cache_lock:
        if time.time() - _device_cache_time < _device_cache_ttl:
            return list(_device_cache)

    adb = find_adb_binary(config)
    devices: list[dict[str, str]] = []
    try:
        result = _run(
            [adb, "devices"],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n")[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) == 2:
                    devices.append({"serial": parts[0], "status": parts[1]})
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        log.warning("Failed to list ADB devices: %s", exc)

    with _device_cache_lock:
        _device_cache = devices
        _device_cache_time = time.time()

    return devices


def is_phone_connected(
    config: AppConfig,
    phone_ip: str,
    adb_port: int = DEFAULT_ADB_PORT,
) -> bool:
    """Check if a specific phone IP:port is connected and authorized."""
    target = f"{phone_ip}:{adb_port}"
    for d in get_adb_devices(config):
        if target in d["serial"] and d["status"] == "device":
            return True
    return False


def get_connected_phone(config: AppConfig) -> tuple[Optional[str], Optional[int]]:
    """
    Return ``(ip, port)`` of the first wirelessly connected device,
    or ``(None, None)`` if none found.
    """
    for d in get_adb_devices(config):
        if d["status"] == "device" and ":" in d["serial"]:
            parts = d["serial"].split(":")
            ip = parts[0]
            try:
                port = int(parts[1])
            except (ValueError, IndexError):
                port = config.get("adb_port", DEFAULT_ADB_PORT)
            return ip, port
    return None, None


# ── Connection Management ─────────────────────────────────────────────────────

def connect(
    config: AppConfig,
    phone_ip: str,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """
    Connect to a phone via ADB wireless.

    Returns ``(success, message)``
    """
    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"

    # Already connected?
    if is_phone_connected(config, phone_ip, adb_port):
        log.info("Phone already connected at %s", target)
        return True, f"Already connected to {target}"

    log.info("Connecting to phone at %s ...", target)
    try:
        result = _run(
            [adb, "connect", target],
            capture_output=True, text=True,
            timeout=ADB_CONNECT_TIMEOUT_SEC,
        )
        output = result.stdout.strip().lower()
        log.debug("ADB connect output: %s", result.stdout.strip())

        if "connected to" in output or "already connected" in output:
            _clear_device_cache()
            return True, f"Connected to {target}"
        else:
            return False, f"Connection failed: {result.stdout.strip()}"
    except FileNotFoundError:
        return False, "ADB binary not found"
    except subprocess.TimeoutExpired:
        return False, f"Connection to {target} timed out"
    except subprocess.SubprocessError as exc:
        return False, f"ADB error: {exc}"


def disconnect(
    config: AppConfig,
    phone_ip: str,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Disconnect a specific device."""
    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"
    try:
        result = _run(
            [adb, "disconnect", target],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        _clear_device_cache()
        return True, f"Disconnected from {target}"
    except subprocess.SubprocessError as exc:
        return False, f"Disconnect failed: {exc}"


def enable_tcpip(
    config: AppConfig,
    serial: Optional[str] = None,
    port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Run `adb tcpip <port>` (USB cable must be attached).

    Mirrors the cable step of the legacy "Scrcpy Wireless" shell script.
    """
    adb = find_adb_binary(config)
    cmd = [adb]
    if serial:
        cmd += ["-s", serial]
    cmd += ["tcpip", str(port)]
    try:
        result = _run(cmd, capture_output=True, text=True,
                      timeout=ADB_COMMAND_TIMEOUT_SEC + 10)
        out = (result.stdout or result.stderr or "").strip()
        ok = result.returncode == 0 or "restarting in TCP mode" in out.lower()
        return ok, out or ("TCP mode on port %d" % port)
    except FileNotFoundError:
        return False, "ADB binary not found"
    except subprocess.SubprocessError as exc:
        return False, f"ADB error: {exc}"


def get_wlan_ip(
    config: AppConfig,
    serial: Optional[str] = None,
) -> Optional[str]:
    """Query the phone's WiFi IP via `adb shell ip addr show wlan0`."""
    import re
    adb = find_adb_binary(config)
    cmd = [adb]
    if serial:
        cmd += ["-s", serial]
    cmd += ["shell", "ip", "addr", "show", "wlan0"]
    try:
        result = _run(cmd, capture_output=True, text=True,
                      timeout=ADB_COMMAND_TIMEOUT_SEC)
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", result.stdout or "")
        return m.group(1) if m else None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def disconnect_all(config: AppConfig) -> None:
    """Disconnect all ADB devices (cleanup on app exit)."""
    adb = find_adb_binary(config)
    try:
        _run(
            [adb, "disconnect"],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        _clear_device_cache()
    except subprocess.SubprocessError:
        pass


# ── Remote Commands ───────────────────────────────────────────────────────────

def send_keyevent(
    config: AppConfig,
    key_code: int,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Send an Android keyevent to the device."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"
    try:
        result = _run(
            [adb, "-s", target, "shell", "input", "keyevent", str(key_code)],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        return result.returncode == 0, result.stdout or result.stderr
    except subprocess.SubprocessError as exc:
        return False, str(exc)


def send_broadcast(
    config: AppConfig,
    action: str,
    extras: Optional[dict[str, str]] = None,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Send an Android broadcast intent."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"
    cmd = [adb, "-s", target, "shell", "am", "broadcast", "-a", action]
    if extras:
        for key, value in extras.items():
            cmd.extend(["--es", key, value])

    try:
        result = _run(
            cmd, capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        return result.returncode == 0, result.stdout.strip()
    except subprocess.SubprocessError as exc:
        return False, str(exc)


def open_url(
    config: AppConfig,
    url: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Open a URL on the phone's browser."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"
    try:
        result = _run(
            [adb, "-s", target, "shell", "am", "start",
             "-a", "android.intent.action.VIEW", "-d", url],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        return result.returncode == 0, f"Opened: {url}"
    except subprocess.SubprocessError as exc:
        return False, str(exc)


# ── Hardware Info ─────────────────────────────────────────────────────────────

def get_hardware_info(
    config: AppConfig,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> dict[str, Any]:
    """
    Query live device specs in a single batched ADB shell command with raw logging.

    Returns a dict with keys: model, android_version, battery_level,
    charging, temperature, resolution, error (if any).
    """
    if not phone_ip:
        phone_ip, port = get_connected_phone(config)
        if port:
            adb_port = port
    if not phone_ip:
        log.warning("[Hardware Telemetry] Cannot fetch info: No device connected.")
        return {"error": "No device connected"}

    adb = find_adb_binary(config)
    
    # Avoid double-port formatting bug (e.g. "192.168.0.100:5555:5555")
    if ":" in phone_ip:
        target = phone_ip
    else:
        target = f"{phone_ip}:{adb_port}"

    info: dict[str, Any] = {"ip": phone_ip, "port": adb_port}

    # Delimited batch query to reliably parse each field regardless of device quirks
    batch_cmd = (
        "echo '===MODEL==='; getprop ro.product.model; "
        "echo '===ANDROID==='; getprop ro.build.version.release; "
        "echo '===BATTERY==='; dumpsys battery 2>/dev/null || cat /sys/class/power_supply/battery/capacity 2>/dev/null; "
        "echo '===SIZE==='; wm size 2>/dev/null"
    )

    try:
        result = _run(
            [adb, "-s", target, "shell", batch_cmd],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC + 3,
        )

        output = result.stdout.strip()
        stderr = result.stderr.strip()

        # RAW LOGGING AS REQUESTED BY USER
        if output:
            log.info("[Hardware Telemetry Raw Response for %s]:\n%s", target, output)
        if stderr:
            log.warning("[Hardware Telemetry Stderr for %s]: %s", target, stderr)

        if result.returncode != 0:
            err_msg = f"ADB command exit {result.returncode}: {stderr or output or 'Unknown error'}"
            log.error("[Hardware Telemetry Failed]: %s", err_msg)
            info["error"] = err_msg
            return info

        import re

        # 1. Model
        model_m = re.search(r"===MODEL===\s*\n([^\n=]+)", output)
        if model_m and model_m.group(1).strip():
            info["model"] = model_m.group(1).strip()
        else:
            info["model"] = "Android Device"

        # 2. Android Version
        ver_m = re.search(r"===ANDROID===\s*\n([^\n=]+)", output)
        if ver_m and ver_m.group(1).strip():
            info["android_version"] = f"Android {ver_m.group(1).strip()}"

        # 3. Battery Level
        lvl = re.search(r"level:\s*(\d+)", output)
        if lvl:
            info["battery_level"] = f"{lvl.group(1)}%"
        else:
            # Fallback for raw capacity numbers
            cap_m = re.search(r"===BATTERY===\s*\n(\d{1,3})\b", output)
            if cap_m:
                info["battery_level"] = f"{cap_m.group(1)}%"
            else:
                info["battery_level"] = "N/A"

        # 4. Charging Status
        st = re.search(r"status:\s*(\d+)", output)
        if st and st.group(1) in ("2", "5"):
            info["charging"] = "Charging"
        elif "charging" in output.lower() and "discharging" not in output.lower():
            info["charging"] = "Charging"
        else:
            info["charging"] = "Discharging"

        # 5. Temperature
        temp = re.search(r"temperature:\s*(\d+)", output)
        if temp:
            try:
                info["temperature"] = f"{int(temp.group(1)) / 10.0:.1f}\u00b0C"
            except ValueError:
                info["temperature"] = "\u2014"
        else:
            info["temperature"] = "\u2014"

        # 6. Screen Resolution
        res = re.search(r"Physical size:\s*(\d+x\d+)", output)
        if res:
            info["resolution"] = res.group(1)

    except FileNotFoundError:
        info["error"] = "ADB binary not found"
        log.error("[Hardware Telemetry] %s", info["error"])
    except subprocess.TimeoutExpired:
        info["error"] = f"ADB timeout while contacting {target}"
        log.error("[Hardware Telemetry] %s", info["error"])
    except subprocess.SubprocessError as exc:
        info["error"] = str(exc)
        log.error("[Hardware Telemetry] Exception: %s", exc)

    return info


# ── Screenshot & Recording ────────────────────────────────────────────────────

def take_screenshot(
    config: AppConfig,
    save_path: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Capture a screenshot from the device and pull it to *save_path*."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"
    remote_path = "/sdcard/scrcpy_screenshot_tmp.png"

    try:
        _run(
            [adb, "-s", target, "shell", "screencap", "-p", remote_path],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        _run(
            [adb, "-s", target, "pull", remote_path, save_path],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        # Clean up remote temp file
        _run(
            [adb, "-s", target, "shell", "rm", remote_path],
            capture_output=True, text=True,
            timeout=ADB_COMMAND_TIMEOUT_SEC,
        )
        log.info("Screenshot saved: %s", save_path)
        return True, f"Screenshot saved: {save_path}"
    except subprocess.SubprocessError as exc:
        return False, f"Screenshot failed: {exc}"


# ── scrcpy Launch ─────────────────────────────────────────────────────────────

_scrcpy_process: Optional[subprocess.Popen] = None
_scrcpy_lock = threading.Lock()


def launch_scrcpy(
    config: AppConfig,
    phone_ip: str,
    adb_port: int = DEFAULT_ADB_PORT,
    extra_args: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """
    Connect to device via ADB and launch scrcpy.

    Returns ``(success, message)``.
    """
    global _scrcpy_process

    # Check if already running
    with _scrcpy_lock:
        if _scrcpy_process is not None and _scrcpy_process.poll() is None:
            return True, "scrcpy is already running"

    # Connect via ADB first
    connected, msg = connect(config, phone_ip, adb_port)
    if not connected:
        return False, msg

    # Save the working IP for next time
    config.update({
        "last_phone_ip": phone_ip,
        "last_phone_port": adb_port,
    })

    # Build scrcpy command (validated against scrcpy v5.0.1 docs).
    scrcpy_bin = find_scrcpy_binary(config)
    cmd = [
        scrcpy_bin,
        "--audio-buffer=50",
        "--audio-output-buffer=10",
        "--no-key-repeat",
        "-s", f"{phone_ip}:{adb_port}",
    ]
    cmd.extend(build_scrcpy_args(config, extra_args))

    try:
        log.info("scrcpy version: %s", get_scrcpy_version(config))
    except Exception:
        pass

    log.info("Launching scrcpy: %s", " ".join(cmd))

    with _scrcpy_lock:
        try:
            _scrcpy_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                **_SUBPROCESS_FLAGS,
            )
            # CRITICAL FIX: Continuously drain stderr in a background daemon thread
            # so the OS kernel pipe buffer (64KB) NEVER fills up and causes scrcpy to freeze!
            def _drain_stderr(proc: subprocess.Popen) -> None:
                try:
                    if proc.stderr:
                        for raw_line in iter(proc.stderr.readline, b""):
                            line = raw_line.decode("utf-8", errors="ignore").strip()
                            if line:
                                log.debug("[scrcpy stderr] %s", line)
                except Exception:
                    pass

            threading.Thread(target=_drain_stderr, args=(_scrcpy_process,), daemon=True).start()

            return True, f"scrcpy launched (PID {_scrcpy_process.pid})"
        except FileNotFoundError:
            return False, f"scrcpy binary not found: {scrcpy_bin}"
        except subprocess.SubprocessError as exc:
            return False, f"Failed to launch scrcpy: {exc}"


def is_scrcpy_running() -> bool:
    """Check if the scrcpy process is still alive."""
    with _scrcpy_lock:
        return _scrcpy_process is not None and _scrcpy_process.poll() is None


def get_scrcpy_pid() -> Optional[int]:
    """Return the PID of the running scrcpy process, or None."""
    with _scrcpy_lock:
        if _scrcpy_process is not None and _scrcpy_process.poll() is None:
            return _scrcpy_process.pid
    return None


def stop_scrcpy() -> None:
    """Terminate the running scrcpy process."""
    global _scrcpy_process
    with _scrcpy_lock:
        if _scrcpy_process is not None:
            try:
                _scrcpy_process.terminate()
                _scrcpy_process.wait(timeout=3)
            except subprocess.SubprocessError:
                try:
                    _scrcpy_process.kill()
                except subprocess.SubprocessError:
                    pass
            _scrcpy_process = None
            log.info("scrcpy process terminated")


def monitor_scrcpy(
    config: AppConfig,
    phone_ip: str,
    adb_port: int,
    on_restart: Optional[callable] = None,
) -> None:
    """
    Monitor scrcpy and restart if it exits unexpectedly.

    Designed to be run in a daemon thread.
    """
    global _scrcpy_process

    while True:
        time.sleep(2)
        with _scrcpy_lock:
            if _scrcpy_process is not None and _scrcpy_process.poll() is not None:
                exit_code = _scrcpy_process.poll()
                log.warning("scrcpy exited (code %d), attempting reconnect...", exit_code)
                _scrcpy_process = None

                if on_restart:
                    on_restart()
                else:
                    launch_scrcpy(config, phone_ip, adb_port)


# ── Phone File Explorer ADB Helpers ───────────────────────────────────────────

def list_phone_dir(
    config: AppConfig,
    remote_path: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> list[dict]:
    """
    List files and directories at `remote_path` on the Android device via ADB.
    Returns list of dicts: {"name": str, "is_dir": bool, "size": int, "date": str}
    """
    if not phone_ip:
        phone_ip, port = get_connected_phone(config)
        if port:
            adb_port = port
    if not phone_ip:
        return []

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"

    # Use toybox ls -l or ls -la with -F or directory test
    cmd = [
        adb, "-s", target, "shell",
        f"ls -l -a '{remote_path}' 2>/dev/null || ls -l '{remote_path}'"
    ]

    items: list[dict] = []
    try:
        res = _run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode != 0 and not res.stdout:
            return []

        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("total "):
                continue

            parts = line.split()
            if len(parts) < 8:
                continue

            perms = parts[0]
            is_dir = perms.startswith("d") or perms.startswith("l")

            # Try to locate size and filename
            # Standard toybox ls -l format:
            # drwxrwx---  3 root  everybody  4096 2026-09-14 12:00 Download
            try:
                # Find the date index (YYYY-MM-DD or Month Day)
                date_str = ""
                name = ""
                # Filename is the last token or tokens joined by space
                # Look for token with '-' (e.g. 2026-09-14) or ':' (e.g. 12:00)
                size = 0
                for i, p in enumerate(parts):
                    if p.isdigit() and int(p) > 0 and i >= 3:
                        size = int(p)
                    if "-" in p and len(p) == 10 and p[:4].isdigit():
                        # Found date like 2026-09-14
                        time_part = parts[i + 1] if i + 1 < len(parts) else ""
                        date_str = f"{p} {time_part}".strip()
                        name = " ".join(parts[i + 2:])
                        break

                if not name:
                    # Fallback
                    name = parts[-1]

                # Filter out current and parent directory dots
                if name in (".", ".."):
                    continue

                # Strip symlink targets if any (e.g., "self -> /storage/emulated/0")
                if " -> " in name:
                    name = name.split(" -> ")[0].strip()

                items.append({
                    "name": name,
                    "is_dir": is_dir,
                    "size": size,
                    "date": date_str,
                })
            except Exception:
                continue

    except Exception as exc:
        log.error("Failed to list remote directory %s: %s", remote_path, exc)

    return items


def pull_from_phone(
    config: AppConfig,
    remote_path: str,
    local_dest: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Pull a file or intact directory tree from Android to PC."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"

    try:
        res = _run(
            [adb, "-s", target, "pull", remote_path, local_dest],
            capture_output=True, text=True, timeout=300,
        )
        if res.returncode == 0:
            return True, f"Pulled to {local_dest}"
        return False, res.stderr or res.stdout
    except Exception as exc:
        return False, str(exc)


def push_to_phone(
    config: AppConfig,
    local_path: str,
    remote_dest: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Push a file or directory tree from PC to Android."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"

    try:
        res = _run(
            [adb, "-s", target, "push", local_path, remote_dest],
            capture_output=True, text=True, timeout=300,
        )
        if res.returncode == 0:
            return True, f"Pushed to {remote_dest}"
        return False, res.stderr or res.stdout
    except Exception as exc:
        return False, str(exc)


def mkdir_on_phone(
    config: AppConfig,
    remote_path: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Create a directory on phone via ADB."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"

    try:
        res = _run(
            [adb, "-s", target, "shell", "mkdir", "-p", remote_path],
            capture_output=True, text=True, timeout=10,
        )
        return res.returncode == 0, res.stdout or res.stderr
    except Exception as exc:
        return False, str(exc)


def delete_on_phone(
    config: AppConfig,
    remote_path: str,
    phone_ip: Optional[str] = None,
    adb_port: int = DEFAULT_ADB_PORT,
) -> tuple[bool, str]:
    """Delete a file or directory on phone via ADB."""
    if not phone_ip:
        phone_ip, _ = get_connected_phone(config)
    if not phone_ip:
        return False, "No phone connected"

    adb = find_adb_binary(config)
    target = f"{phone_ip}:{adb_port}"

    try:
        res = _run(
            [adb, "-s", target, "shell", "rm", "-rf", remote_path],
            capture_output=True, text=True, timeout=15,
        )
        return res.returncode == 0, res.stdout or res.stderr
    except Exception as exc:
        return False, str(exc)

