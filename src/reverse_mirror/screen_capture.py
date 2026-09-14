"""
High-performance Screen Capture module for CelSuite Reverse Mirror.
Supports Windows (DXGI / mss) and Linux (X11 / PipeWire / mss).
"""

from __future__ import annotations

import sys
import time
from typing import Optional, Tuple, List, Dict

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

from src.logger import get_logger

log = get_logger(__name__)


class ScreenCapture:
    """
    Captures desktop frames at high framerates with minimal latency.
    """

    def __init__(self, monitor_index: int = 1) -> None:
        self.monitor_index = monitor_index
        self._sct = None
        self._running = False
        self._current_monitor = None
        self._init_backend()

    def _init_backend(self) -> None:
        if HAS_MSS:
            try:
                self._sct = mss.mss()
                monitors = self._sct.monitors
                if self.monitor_index < len(monitors):
                    self._current_monitor = monitors[self.monitor_index]
                else:
                    self._current_monitor = monitors[0]
                log.info("ScreenCapture initialized with mss backend (Monitor: %s)", self._current_monitor)
            except Exception as e:
                log.error("Failed to initialize mss capture backend: %s", e)
                self._sct = None
        else:
            log.warning("mss library not installed; screen capture requires mss or native fallback")

    def get_monitors(self) -> List[Dict[str, int]]:
        """Return list of available displays."""
        if not self._sct:
            return [{"id": 0, "name": "Primary Display", "width": 1920, "height": 1080}]
        results = []
        for i, m in enumerate(self._sct.monitors[1:], start=1):
            results.append({
                "id": i,
                "name": f"Monitor {i} ({m['width']}x{m['height']})",
                "width": m["width"],
                "height": m["height"],
                "top": m["top"],
                "left": m["left"],
            })
        return results if results else [{"id": 0, "name": "All Monitors (Merged)", "width": self._sct.monitors[0]["width"], "height": self._sct.monitors[0]["height"]}]

    def set_monitor(self, index: int) -> None:
        """Switch the captured display."""
        if self._sct and index < len(self._sct.monitors):
            self.monitor_index = index
            self._current_monitor = self._sct.monitors[index]
            log.info("Switched capture to monitor %d: %s", index, self._current_monitor)

    def capture_raw_bgra(self) -> Optional[Tuple[bytes, int, int]]:
        """
        Capture the current frame as raw BGRA bytes.
        Returns (raw_bytes, width, height) or None on failure.
        """
        if not self._sct or not self._current_monitor:
            return None
        try:
            sct_img = self._sct.grab(self._current_monitor)
            return sct_img.raw, sct_img.width, sct_img.height
        except Exception as e:
            log.debug("Frame grab exception: %s", e)
            return None

    def close(self) -> None:
        """Release capture resources."""
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
