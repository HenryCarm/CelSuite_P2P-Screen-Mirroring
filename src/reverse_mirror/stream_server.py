"""
Reverse Stream Server for CelSuite (PC -> Phone Stream Coordinator).
Coordinates ScreenCapture, VideoEncoder, AudioStreamer, and InputInjector.
Streams raw H.264 video chunks & Opus/PCM audio over UDP and listens for phone input.
"""

from __future__ import annotations

import math
import socket
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.constants import (
    DEFAULT_REVERSE_VIDEO_PORT,
    DEFAULT_REVERSE_AUDIO_PORT,
    DEFAULT_REVERSE_INPUT_PORT,
)
from src.logger import get_logger
from src.reverse_mirror.screen_capture import ScreenCapture
from src.reverse_mirror.video_encoder import VideoEncoder
from src.reverse_mirror.audio_streamer import AudioStreamer
from src.reverse_mirror.input_injector import InputInjector

log = get_logger(__name__)


class ReverseStreamServer(QObject):
    """
    Qt-compatible Reverse Mirror Server.
    Runs on the PC, broadcasts desktop stream to phone, and processes mobile touch/keys.
    """

    # Signals for UI status display
    stream_started = Signal(str, int)     # client_ip, fps
    stream_stopped = Signal()
    stats_updated = Signal(float, int)    # current_fps, bitrate_kbps
    client_connected = Signal(str)        # client_ip
    client_disconnected = Signal()

    def __init__(
        self,
        fps: int = 60,
        bitrate_kbps: int = 6000,
        monitor_index: int = 1,
        enable_audio: bool = True,
    ) -> None:
        super().__init__()
        self.fps = fps
        self.bitrate_kbps = bitrate_kbps
        self.monitor_index = monitor_index
        self.enable_audio = enable_audio

        self._running = False
        self._client_ip: Optional[str] = None

        self._capture = ScreenCapture(monitor_index=self.monitor_index)
        self._encoder: Optional[VideoEncoder] = None
        self._audio: Optional[AudioStreamer] = None
        self._injector = InputInjector()

        self._video_sock: Optional[socket.socket] = None
        self._audio_sock: Optional[socket.socket] = None
        self._input_sock: Optional[socket.socket] = None

        self._capture_thread: Optional[threading.Thread] = None
        self._input_thread: Optional[threading.Thread] = None

        self._frame_count = 0
        self._last_fps_time = time.time()

    def set_client(self, client_ip: str) -> None:
        """Set the target phone IP for streaming."""
        self._client_ip = client_ip
        log.info("ReverseStreamServer target client set to: %s", client_ip)

    def start(self, client_ip: Optional[str] = None) -> bool:
        """Start screen capture and streaming."""
        if self._running:
            return True

        if client_ip:
            self._client_ip = client_ip

        if not self._client_ip:
            log.warning("Cannot start ReverseStreamServer: No target phone IP specified!")
            return False

        # 1. Grab initial frame to determine dimensions
        initial = self._capture.capture_raw_bgra()
        if not initial:
            log.error("Failed to capture initial frame from desktop!")
            return False

        _, width, height = initial
        self._injector.set_screen_dimensions(width, height)

        # 2. Setup UDP sockets
        try:
            self._video_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                self._video_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2 * 1024 * 1024)
            except Exception:
                pass
            self._audio_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Input listener socket (listens on PC port 5562)
            self._input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._input_sock.bind(("0.0.0.0", DEFAULT_REVERSE_INPUT_PORT))
            self._input_sock.settimeout(1.0)
        except Exception as e:
            log.error("Failed to initialize streaming sockets: %s", e)
            self.stop()
            return False

        # 3. Setup Video Encoder
        self._encoder = VideoEncoder(
            width=width,
            height=height,
            fps=self.fps,
            bitrate_kbps=self.bitrate_kbps,
            on_nal_packet=self._send_video_packet,
        )
        if not self._encoder.start():
            self.stop()
            return False

        # 4. Setup Audio Streamer (if enabled)
        if self.enable_audio:
            self._audio = AudioStreamer(on_audio_packet=self._send_audio_packet)
            self._audio.start()

        self._running = True

        # 5. Launch threads
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="ScreenCaptureLoop"
        )
        self._capture_thread.start()

        self._input_thread = threading.Thread(
            target=self._input_listener_loop, daemon=True, name="InputListenerLoop"
        )
        self._input_thread.start()

        self.stream_started.emit(self._client_ip, self.fps)
        log.info("ReverseStreamServer actively streaming to %s (%dx%d @ %d FPS)", self._client_ip, width, height, self.fps)
        return True

    def _send_video_packet(self, chunk: bytes) -> None:
        """Send H.264 slice chunk over UDP with CelSuite Stream Protocol v1 header."""
        if not self._running or not self._video_sock or not self._client_ip:
            return
        try:
            import struct
            # CelSuite Stream Protocol v1: !4sIIHHQ (24 bytes)
            # magic(4), frame_id(4), chunk_idx(2), total_chunks(2), payload_len(2), flags(2), timestamp_us(8)
            max_payload = 1380
            total_len = len(chunk)
            total_chunks = max(1, math.ceil(total_len / max_payload))
            ts_us = int(time.time() * 1_000_000)

            for idx in range(total_chunks):
                start = idx * max_payload
                part = chunk[start : start + max_payload]
                flags = 0x01 if (part.startswith(b"\x00\x00\x00\x01\x67") or part.startswith(b"\x00\x00\x00\x01\x65")) else 0x00
                header = struct.pack("!4sIIHHQ", b"CELV", self._frame_count, idx, total_chunks, flags, ts_us)
                self._video_sock.sendto(header + part, (self._client_ip, DEFAULT_REVERSE_VIDEO_PORT))
        except Exception as e:
            log.debug("Video packet send error: %s", e)

    def _send_audio_packet(self, data: bytes) -> None:
        """Send audio chunk over UDP."""
        if not self._running or not self._audio_sock or not self._client_ip:
            return
        try:
            self._audio_sock.sendto(data, (self._client_ip, DEFAULT_REVERSE_AUDIO_PORT))
        except Exception as e:
            log.debug("Audio packet send error: %s", e)

    def _capture_loop(self) -> None:
        """Main 60 FPS screen capture and encoder feeder loop."""
        frame_interval = 1.0 / max(1, self.fps)
        self._last_fps_time = time.time()
        self._frame_count = 0

        while self._running:
            t_start = time.time()

            frame_data = self._capture.capture_raw_bgra()
            if frame_data and self._encoder:
                raw_bytes, _, _ = frame_data
                self._encoder.push_frame(raw_bytes)
                self._frame_count += 1

            # Telemetry FPS calculation
            now = time.time()
            if now - self._last_fps_time >= 1.0:
                calc_fps = self._frame_count / (now - self._last_fps_time)
                self.stats_updated.emit(calc_fps, self.bitrate_kbps)
                self._frame_count = 0
                self._last_fps_time = now

            # Sleep remainder of frame duration
            elapsed = time.time() - t_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0.001:
                time.sleep(sleep_time)

    def _input_listener_loop(self) -> None:
        """Listens for touch and keyboard commands from the phone."""
        while self._running and self._input_sock:
            try:
                data, addr = self._input_sock.recvfrom(4096)
                if not data:
                    continue

                msg = data.decode("utf-8", errors="ignore").strip()
                self._dispatch_input_command(msg)
            except socket.timeout:
                continue
            except Exception as e:
                log.debug("Input listener exception: %s", e)

    def _dispatch_input_command(self, cmd: str) -> None:
        """
        Parse and execute incoming touch or key command.
        Examples:
          TOUCH|id|DOWN|norm_x|norm_y
          MOUSE|MOVE_REL|dx|dy
          MOUSE|CLICK|0|0
          KEY|TAP|enter
          MACRO|alt_tab
        """
        try:
            parts = cmd.split("|")
            kind = parts[0]

            if kind == "TOUCH" and len(parts) >= 5:
                touch_id = int(parts[1])
                action = parts[2]
                norm_x = float(parts[3])
                norm_y = float(parts[4])
                self._injector.handle_touch_event(touch_id, action, norm_x, norm_y)

            elif kind == "MOUSE" and len(parts) >= 4:
                action = parts[1]
                p1 = float(parts[2])
                p2 = float(parts[3])
                self._injector.handle_mouse_event(action, p1, p2)

            elif kind == "KEY" and len(parts) >= 3:
                action = parts[1]
                key_name = parts[2]
                self._injector.handle_key_event(action, key_name)

            elif kind == "MACRO" and len(parts) >= 2:
                macro_name = parts[1]
                self._injector.handle_macro(macro_name)

        except Exception as e:
            log.debug("Failed to dispatch input command '%s': %s", cmd, e)

    def stop(self) -> None:
        """Stop all streaming and input threads."""
        self._running = False

        if self._encoder:
            self._encoder.stop()
            self._encoder = None

        if self._audio:
            self._audio.stop()
            self._audio = None

        if self._capture:
            self._capture.close()

        for s in (self._video_sock, self._audio_sock, self._input_sock):
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        self._video_sock = None
        self._audio_sock = None
        self._input_sock = None

        self.stream_stopped.emit()
        log.info("ReverseStreamServer stopped completely")
