"""
PC → Phone live screen mirror (TCP MJPEG).

Why a second path next to ``stream_server.ReverseStreamServer`` (UDP H.264)?
The H.264/UDP path has no decoder on the phone side — the Android
``PCMirrorScreen`` never displayed video, it only sent input. This module
is the *actual* mirror: the PC captures with ``mss``, JPEG-encodes with
Pillow, and serves length-prefixed frames over TCP. The phone connects,
decodes with its built-in JPEG decoder, and shows live video with
touch forwarded back to the PC input port (5562).

Protocol (all big-endian)::
    HELLO  : b"CELJ" + u16 width + u16 height            (once per client)
    FRAME* : u32 jpeg_len + jpeg_bytes                   (repeated)

Desktop preview reuses the same JPEG bytes via ``frame_ready``.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from io import BytesIO
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.constants import DEFAULT_MIRROR_VIDEO_PORT
from src.logger import get_logger
from src.reverse_mirror.screen_capture import ScreenCapture

log = get_logger(__name__)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    HAS_PIL = False

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class PCMirrorServer(QObject):
    """TCP MJPEG server: one phone client at a time + local preview signal."""

    frame_ready = Signal(bytes, int, int)  # jpeg, width, height
    stats_updated = Signal(float, int)  # fps, kbps (approx)
    client_connected = Signal(str)
    client_disconnected = Signal()
    stream_stopped = Signal()

    def __init__(
        self,
        fps: int = 60,
        quality: int = 65,
        max_width: int = 1280,
        monitor_index: int = 1,
        port: int = DEFAULT_MIRROR_VIDEO_PORT,
    ) -> None:
        super().__init__()
        self.fps = max(10, min(60, fps))
        self.quality = max(30, min(95, quality))
        self.max_width = max_width
        self.monitor_index = monitor_index
        self.port = port
        self._running = False
        self._capture = ScreenCapture(monitor_index=monitor_index)
        self._srv_sock: Optional[socket.socket] = None
        self._client: Optional[socket.socket] = None
        self._client_ip: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._frames = 0
        self._bytes = 0
        self._t0 = time.time()

    # ── Public ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Bind the TCP port and start the serve loop. Phone connects to us."""
        if self._running:
            return True
        if not HAS_PIL:
            log.error("Pillow is required for PC mirror (pip install Pillow)")
            return False
        try:
            self._srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv_sock.bind(("0.0.0.0", self.port))
            self._srv_sock.listen(1)
            self._srv_sock.settimeout(1.0)
        except OSError as exc:
            log.error("Mirror server bind failed on port %d: %s", self.port, exc)
            return False
        self._running = True
        self._t0 = time.time()
        self._thread = threading.Thread(
            target=self._serve_loop, daemon=True, name="PCMirrorServer"
        )
        self._thread.start()
        log.info(
            "PC mirror listening on port %d — open 'Watch PC' on the phone",
            self.port,
        )
        return True

    def stop(self) -> None:
        self._running = False
        for s in (self._client, self._srv_sock):
            try:
                if s:
                    s.close()
            except OSError:
                pass
        self._client = None
        self._srv_sock = None
        try:
            self._capture.close()
        except Exception:
            pass
        self.stream_stopped.emit()
        log.info("PC mirror stopped")

    @property
    def has_client(self) -> bool:
        return self._client is not None

    # ── Loop ────────────────────────────────────────────────────────────

    def _serve_loop(self) -> None:
        interval = 1.0 / max(1, self.fps)
        while self._running:
            if self._client is None:
                try:
                    assert self._srv_sock is not None
                    conn, addr = self._srv_sock.accept()
                    # Low latency gaming: disable Nagle algorithm
                    try:
                        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    except Exception:
                        pass
                    self._client = conn
                    self._client_ip = addr[0]
                    self._client.settimeout(5.0)
                    self._hello_sent = False
                    self.client_connected.emit(addr[0])
                    log.info("Phone watching PC screen with Low-Latency Engine: %s", addr[0])
                except socket.timeout:
                    continue
                except OSError:
                    break
            t_start = time.time()
            ok = self._grab_and_send()
            if not ok:  # client gone — drop and wait for next
                try:
                    if self._client:
                        self._client.close()
                except OSError:
                    pass
                self._client = None
                if self._client_ip:
                    self.client_disconnected.emit()
                    log.info("Phone stopped watching")
                    self._client_ip = None
                continue
            # Stats ~1/s
            now = time.time()
            if now - self._t0 >= 1.0 and self._frames:
                fps = self._frames / (now - self._t0)
                kbps = int(self._bytes * 8 / (now - self._t0) / 1000)
                self.stats_updated.emit(fps, kbps)
                self._frames, self._bytes, self._t0 = 0, 0, now
            dt = time.time() - t_start
            if dt < interval:
                time.sleep(interval - dt)

    def _grab_and_send(self) -> bool:
        frame = self._capture.capture_raw_bgra()
        if not frame:
            time.sleep(0.01)
            return True
        raw, w, h = frame
        jpg = None

        # 1. OpenCV High-Performance Path (3x faster, ~20ms encode)
        if HAS_CV2:
            try:
                arr = np.frombuffer(raw, dtype=np.uint8).reshape((h, w, 4))
                bgr = arr[:, :, :3]
                if self.max_width and w > self.max_width:
                    nh = int(h * self.max_width / w)
                    bgr = cv2.resize(bgr, (self.max_width, nh), interpolation=cv2.INTER_LINEAR)
                    w, h = self.max_width, nh
                ok, buf = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, self.quality, cv2.IMWRITE_JPEG_OPTIMIZE, 0])
                if ok:
                    jpg = buf.tobytes()
            except Exception as exc:
                log.debug("OpenCV encode error: %s", exc)
                jpg = None

        # 2. PIL Fallback
        if jpg is None and HAS_PIL:
            try:
                img = Image.frombuffer("RGBA", (w, h), raw, "raw", "BGRA")
                if self.max_width and w > self.max_width:
                    nh = int(h * self.max_width / w)
                    img = img.resize((self.max_width, nh))
                    w, h = self.max_width, nh
                buf = BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=self.quality)
                jpg = buf.getvalue()
            except Exception as exc:
                log.debug("JPEG encode failed: %s", exc)
                return True

        if not jpg:
            return True

        self.frame_ready.emit(jpg, w, h)
        if self._client is None:
            return True
        try:
            if not getattr(self, "_hello_sent", False):
                self._client.sendall(b"CELJ" + struct.pack("!HH", w, h))
                self._hello_sent = True
            self._client.sendall(struct.pack("!I", len(jpg)) + jpg)
            self._frames += 1
            self._bytes += len(jpg)
            return True
        except (OSError, ConnectionError):
            self._hello_sent = False
            return False
