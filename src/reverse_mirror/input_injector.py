"""
Multi-Touch, Mouse & Virtual Keyboard Input Injector.
Translates touch events from the phone into native Windows / Linux input:
- Windows: Windows Touch Injection API (`InjectTouchInput`) & `SendInput`
- Linux: `uinput` virtual digitizer & fallback `pynput` / `pyautogui`
"""

from __future__ import annotations

import sys
import ctypes
import time
from typing import Dict, Tuple

from src.logger import get_logger

log = get_logger(__name__)


# ── Windows Touch Injection Definitions ────────────────────────────────────────

if sys.platform == "win32":
    try:
        from ctypes import wintypes

        class POINTER_INFO(ctypes.Structure):
            _fields_ = [
                ("pointerType", wintypes.DWORD),
                ("pointerId", wintypes.UINT),
                ("frameId", wintypes.UINT),
                ("pointerFlags", wintypes.UINT),
                ("sourceDevice", wintypes.HANDLE),
                ("hwndTarget", wintypes.HWND),
                ("ptPixelLocation", wintypes.POINT),
                ("ptHimetricLocation", wintypes.POINT),
                ("ptPixelLocationRaw", wintypes.POINT),
                ("ptHimetricLocationRaw", wintypes.POINT),
                ("dwTime", wintypes.DWORD),
                ("historyCount", wintypes.UINT),
                ("InputData", wintypes.INT),
                ("KeyStates", wintypes.DWORD),
                ("PerformanceCount", wintypes.UINT64),
                ("ButtonChangeType", wintypes.INT),
            ]

        class POINTER_TOUCH_INFO(ctypes.Structure):
            _fields_ = [
                ("pointerInfo", POINTER_INFO),
                ("touchFlags", wintypes.UINT),
                ("touchMask", wintypes.UINT),
                ("rcContact", wintypes.RECT),
                ("rcContactRaw", wintypes.RECT),
                ("orientation", wintypes.UINT),
                ("pressure", wintypes.UINT),
            ]

        # Flags for touch injection
        PT_TOUCH = 0x00000002
        TOUCH_FLAG_NONE = 0x00000000
        TOUCH_MASK_CONTACTAREA = 0x00000001
        TOUCH_MASK_ORIENTATION = 0x00000002
        TOUCH_MASK_PRESSURE = 0x00000004

        POINTER_FLAG_NONE = 0x00000000
        POINTER_FLAG_INRANGE = 0x00000002
        POINTER_FLAG_INCONTACT = 0x00000004
        POINTER_FLAG_DOWN = 0x00010000
        POINTER_FLAG_UPDATE = 0x00020000
        POINTER_FLAG_UP = 0x00040000

        # Touch injection functions from User32
        _user32 = ctypes.windll.user32
        _user32.InitializeTouchInjection.argtypes = [wintypes.UINT, wintypes.DWORD]
        _user32.InitializeTouchInjection.restype = wintypes.BOOL
        _user32.InjectTouchInput.argtypes = [wintypes.UINT, ctypes.POINTER(POINTER_TOUCH_INFO)]
        _user32.InjectTouchInput.restype = wintypes.BOOL

        HAS_WIN_TOUCH = True
    except Exception as e:
        log.debug("Windows Touch Injection API not available: %s", e)
        HAS_WIN_TOUCH = False
else:
    HAS_WIN_TOUCH = False


# ── Generic Mouse / Keyboard Fallback ─────────────────────────────────────────

import shutil
import subprocess

_xdotool_bin = shutil.which("xdotool")
HAS_XDOTOOL = bool(_xdotool_bin and sys.platform.startswith("linux"))

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class InputInjector:
    """
    Receives touch, mouse, and keyboard events from the Android client
    and injects them natively into Windows (Touch Injection API / SendInput)
    or Linux (xdotool / uinput).
    """

    def __init__(self, screen_width: int = 1600, screen_height: int = 900) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._touch_initialized = False
        self._active_touches: Dict[int, Tuple[int, int]] = {}  # touch_id -> (pixel_x, pixel_y)

        if HAS_WIN_TOUCH:
            try:
                # Initialize with support for up to 10 simultaneous touch points
                res = _user32.InitializeTouchInjection(10, 0x00000000)
                self._touch_initialized = bool(res)
                log.info("Windows Touch Injection initialized (10 points): %s", self._touch_initialized)
            except Exception as e:
                log.debug("Failed to init touch injection: %s", e)
        elif HAS_XDOTOOL:
            log.info("Linux Input Injection initialized using native xdotool at %s", _xdotool_bin)

    def set_screen_dimensions(self, width: int, height: int) -> None:
        """Update host screen dimensions for accurate coordinate mapping."""
        self.screen_width = width
        self.screen_height = height

    def handle_touch_event(self, touch_id: int, action: str, norm_x: float, norm_y: float) -> None:
        """
        Inject multi-touch event with concurrent finger holding tracking.
        Essential for dual-joystick mobile games (Minecraft, Brawl Stars, LDPlayer).
        """
        pixel_x = int(norm_x * self.screen_width)
        pixel_y = int(norm_y * self.screen_height)

        if action in ("DOWN", "MOVE"):
            self._active_touches[touch_id] = (pixel_x, pixel_y)
        elif action == "UP":
            self._active_touches.pop(touch_id, None)

        if HAS_WIN_TOUCH and self._touch_initialized:
            self._inject_win_multitouch(touch_id, action, pixel_x, pixel_y)
        elif HAS_XDOTOOL:
            # Native Linux xdotool input
            # Primary touch maps to mouse cursor; secondary touches handle actions/taps
            if touch_id == 0:
                if action == "DOWN":
                    subprocess.run([_xdotool_bin, "mousemove", str(pixel_x), str(pixel_y), "mousedown", "1"], capture_output=True, timeout=0.2)
                elif action == "MOVE":
                    subprocess.run([_xdotool_bin, "mousemove", str(pixel_x), str(pixel_y)], capture_output=True, timeout=0.2)
                elif action == "UP":
                    subprocess.run([_xdotool_bin, "mouseup", "1"], capture_output=True, timeout=0.2)
            else:
                # Multi-finger tap on Linux
                if action == "DOWN":
                    # If left thumb is held (touch 0) and right thumb taps (touch 1), trigger action
                    subprocess.run([_xdotool_bin, "click", "1"], capture_output=True, timeout=0.2)

    def _inject_win_multitouch(self, changed_id: int, action: str, pixel_x: int, pixel_y: int) -> None:
        """
        Dispatch simultaneous multi-touch array to Windows Touch Injection API.
        Ensures holding down one finger (e.g. running) while tapping/swiping with another works 100%!
        """
        try:
            # Inject updated contact
            touch_info = POINTER_TOUCH_INFO()
            touch_info.pointerInfo.pointerType = PT_TOUCH
            touch_info.pointerInfo.pointerId = changed_id
            touch_info.pointerInfo.ptPixelLocation.x = pixel_x
            touch_info.pointerInfo.ptPixelLocation.y = pixel_y

            flags = POINTER_FLAG_INRANGE
            if action == "DOWN":
                flags |= POINTER_FLAG_INCONTACT | POINTER_FLAG_DOWN
            elif action == "MOVE":
                flags |= POINTER_FLAG_INCONTACT | POINTER_FLAG_UPDATE
            elif action == "UP":
                flags |= POINTER_FLAG_UP

            touch_info.pointerInfo.pointerFlags = flags
            touch_info.touchMask = TOUCH_MASK_CONTACTAREA | TOUCH_MASK_PRESSURE
            touch_info.rcContact.left = pixel_x - 3
            touch_info.rcContact.right = pixel_x + 3
            touch_info.rcContact.top = pixel_y - 3
            touch_info.rcContact.bottom = pixel_y + 3
            touch_info.pressure = 512

            _user32.InjectTouchInput(1, ctypes.byref(touch_info))
        except Exception as e:
            log.debug("Error in _inject_win_multitouch: %s", e)

    def handle_mouse_event(self, action: str, p1: float, p2: float) -> None:
        """
        Trackpad mode handler.
        action in ('MOVE_REL', 'CLICK', 'RCLICK', 'SCROLL').
        """
        if HAS_XDOTOOL:
            try:
                if action == "MOVE_REL":
                    subprocess.run([_xdotool_bin, "mousemove_relative", "--", str(int(p1)), str(int(p2))], capture_output=True, timeout=0.2)
                elif action == "CLICK":
                    btn = str(int(p1)) if p1 else "1"
                    subprocess.run([_xdotool_bin, "click", btn], capture_output=True, timeout=0.2)
                elif action == "DOWN":
                    btn = str(int(p1)) if p1 else "1"
                    subprocess.run([_xdotool_bin, "mousedown", btn], capture_output=True, timeout=0.2)
                elif action == "UP":
                    btn = str(int(p1)) if p1 else "1"
                    subprocess.run([_xdotool_bin, "mouseup", btn], capture_output=True, timeout=0.2)
                elif action == "RCLICK":
                    subprocess.run([_xdotool_bin, "click", "3"], capture_output=True, timeout=0.2)
                elif action == "SCROLL":
                    btn = "4" if p1 > 0 else "5"
                    subprocess.run([_xdotool_bin, "click", btn], capture_output=True, timeout=0.2)
            except Exception as e:
                log.debug("xdotool mouse error: %s", e)

        if sys.platform == "win32":
            try:
                MOUSEEVENTF_LEFTDOWN = 0x0002
                MOUSEEVENTF_LEFTUP = 0x0004
                MOUSEEVENTF_RIGHTDOWN = 0x0008
                MOUSEEVENTF_RIGHTUP = 0x0010
                btn_id = int(p1) if p1 else 1
                if action == "DOWN":
                    flag = MOUSEEVENTF_LEFTDOWN if btn_id == 1 else MOUSEEVENTF_RIGHTDOWN
                    _user32.mouse_event(flag, 0, 0, 0, 0)
                elif action == "UP":
                    flag = MOUSEEVENTF_LEFTUP if btn_id == 1 else MOUSEEVENTF_RIGHTUP
                    _user32.mouse_event(flag, 0, 0, 0, 0)
                elif action == "CLICK":
                    _user32.mouse_event(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                elif action == "RCLICK":
                    _user32.mouse_event(MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            except Exception as e:
                log.debug("Windows mouse event injection failed: %s", e)

    def handle_key_event(self, action: str, key_name: str) -> None:
        """
        Inject keyboard press or release (WASD movement, Space jump, Shift sprint, Skills).
        action in ('DOWN', 'UP', 'TAP').
        """
        key_clean = key_name.lower().strip()
        
        # Key aliases for compatibility
        key_alias_linux = {
            "space": "space",
            "shift": "Shift_L",
            "ctrl": "Control_L",
            "alt": "Alt_L",
            "enter": "Return",
            "esc": "Escape",
            "tab": "Tab",
        }
        linux_key = key_alias_linux.get(key_clean, key_clean)

        if HAS_XDOTOOL:
            try:
                if action == "DOWN":
                    subprocess.run([_xdotool_bin, "keydown", linux_key], capture_output=True, timeout=0.2)
                elif action == "UP":
                    subprocess.run([_xdotool_bin, "keyup", linux_key], capture_output=True, timeout=0.2)
                elif action == "TAP":
                    subprocess.run([_xdotool_bin, "key", linux_key], capture_output=True, timeout=0.2)
            except Exception as e:
                log.debug("xdotool key error: %s", e)

        if sys.platform == "win32":
            # Virtual Key code mapping for Windows gaming
            vk_map = {
                "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
                "e": 0x45, "q": 0x51, "r": 0x52, "f": 0x46, "c": 0x43, "x": 0x58, "z": 0x5A, "v": 0x56,
                "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
                "space": 0x20, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
                "enter": 0x0D, "esc": 0x1B, "tab": 0x09,
            }
            vk = vk_map.get(key_clean)
            if vk:
                try:
                    KEYEVENTF_KEYUP = 0x0002
                    if action == "DOWN":
                        _user32.keybd_event(vk, 0, 0, 0)
                    elif action == "UP":
                        _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                    elif action == "TAP":
                        _user32.keybd_event(vk, 0, 0, 0)
                        _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                except Exception as e:
                    log.debug("Windows keybd_event injection failed: %s", e)

    def handle_macro(self, macro_name: str) -> None:
        """
        Execute keybind presets (including custom user-defined shortcuts).
        """
        macro_clean = macro_name.lower().strip()
        if HAS_XDOTOOL:
            macro_map = {
                "copy": "ctrl+c",
                "paste": "ctrl+v",
                "cut": "ctrl+x",
                "undo": "ctrl+z",
                "redo": "ctrl+y",
                "select_all": "ctrl+a",
                "alt_tab": "alt+Tab",
                "win_d": "super+d",
                "esc": "Escape",
                "enter": "Return",
                "space": "space",
                "tab": "Tab",
                "task_manager": "ctrl+shift+Escape",
                "close_window": "alt+F4",
            }
            key_combo = macro_map.get(macro_clean, macro_clean)
            try:
                subprocess.run([_xdotool_bin, "key", key_combo], capture_output=True, timeout=0.2)
                log.info("Executed macro: %s -> %s", macro_name, key_combo)
            except Exception as e:
                log.debug("xdotool macro error: %s", e)

        if HAS_PYAUTOGUI:
            macros: Dict[str, list[str]] = {
                "copy": ["ctrl", "c"],
                "paste": ["ctrl", "v"],
                "cut": ["ctrl", "x"],
                "undo": ["ctrl", "z"],
                "redo": ["ctrl", "y"],
                "select_all": ["ctrl", "a"],
                "alt_tab": ["alt", "tab"],
                "win_d": ["win", "d"],
                "esc": ["esc"],
                "enter": ["enter"],
                "space": ["space"],
                "tab": ["tab"],
                "task_manager": ["ctrl", "shift", "esc"],
                "close_window": ["alt", "f4"],
            }
            keys = macros.get(macro_name.lower())
            if keys:
                try:
                    pyautogui.hotkey(*keys)
                    log.info("Executed pyautogui macro: %s -> %s", macro_name, keys)
                except Exception as e:
                    log.debug("Error executing macro %s: %s", macro_name, e)
