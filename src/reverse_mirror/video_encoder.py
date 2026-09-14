"""
Low-Latency Video Encoder for CelSuite Reverse Mirror.
Encodes raw desktop frames into ultra-low-latency H.264 streams
using hardware GPU acceleration (NVENC, QSV, AMF) or fast CPU fallback.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from typing import Optional, Callable

from src.logger import get_logger

log = get_logger(__name__)


class VideoEncoder:
    """
    Subprocess-based zero-latency H.264 encoder.
    Pipes raw BGRA frames directly to ffmpeg and yields NAL packets.
    """

    def __init__(
        self,
        width: int,
        height: int,
        fps: int = 60,
        bitrate_kbps: int = 6000,
        on_nal_packet: Optional[Callable[[bytes], None]] = None,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate_kbps = bitrate_kbps
        self.on_nal_packet = on_nal_packet

        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        self._encoder_codec = self._detect_best_codec()

    def _detect_best_codec(self) -> str:
        """
        Probe for GPU hardware acceleration with a real 1-frame test
        to prevent selecting codecs supported by FFmpeg binary but missing from GPU hardware.
        """
        codecs_to_test = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_vaapi", "libx264"]
        for c in codecs_to_test:
            try:
                cmd = [
                    self._ffmpeg_bin,
                    "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30",
                    "-t", "0.04",
                    "-c:v", c,
                    "-f", "null", "-",
                ]
                kwargs = {"capture_output": True, "timeout": 2}
                if sys.platform == "win32":
                    kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
                res = subprocess.run(cmd, **kwargs)
                if res.returncode == 0:
                    log.info("Hardware probe verified functional video encoder: %s", c)
                    return c
            except Exception:
                continue
        log.warning("Hardware video encoders unavailable; falling back to libx264")
        return "libx264"

    def start(self) -> bool:
        """Start the ffmpeg encoding pipeline."""
        if self._running:
            return True

        # Build ffmpeg command line tuned specifically for the host CPU/GPU
        cmd = [
            self._ffmpeg_bin,
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "pipe:0",  # Input from stdin
            "-c:v", self._encoder_codec,
            "-b:v", f"{self.bitrate_kbps}k",
            "-maxrate", f"{self.bitrate_kbps * 2}k",
            "-bufsize", f"{self.bitrate_kbps // 2}k",
            "-pix_fmt", "yuv420p",
            "-g", str(self.fps),       # Keyframe every 1 second
            "-bf", "0",                # No B-frames for zero latency
        ]

        if self._encoder_codec == "libx264":
            # Tuned specifically for Intel Core i5 (dual-core 4-thread):
            # 3 threads leaves 1 thread completely free for host OS/apps to prevent micro-stutter
            cmd.extend([
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-threads", "3",
                "-crf", "23",
            ])
        elif self._encoder_codec == "h264_nvenc":
            cmd.extend(["-preset", "p1", "-tune", "ull", "-zerolatency", "1"])
        elif self._encoder_codec == "h264_qsv":
            cmd.extend(["-preset", "veryfast", "-low_power", "1"])

        # Output raw Annex-B H.264 stream to stdout
        cmd.extend(["-f", "h264", "pipe:1"])

        try:
            kwargs = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "bufsize": 1048576,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

            self._proc = subprocess.Popen(cmd, **kwargs)
            self._running = True

            self._reader_thread = threading.Thread(
                target=self._stdout_reader_loop, daemon=True, name="VideoEncoderReader"
            )
            self._reader_thread.start()
            log.info("VideoEncoder started (%dx%d @ %d FPS, %s, %d kbps)", self.width, self.height, self.fps, self._encoder_codec, self.bitrate_kbps)
            return True
        except Exception as e:
            log.error("Failed to start ffmpeg video encoder: %s", e)
            self._running = False
            return False

    def push_frame(self, bgra_bytes: bytes) -> bool:
        """Feed a raw frame to the encoder."""
        if not self._running or not self._proc or not self._proc.stdin:
            return False
        try:
            self._proc.stdin.write(bgra_bytes)
            self._proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError) as e:
            log.debug("Encoder pipe error on push_frame: %s", e)
            self.stop()
            return False

    def _stdout_reader_loop(self) -> None:
        """Continuously read encoded H.264 stream from ffmpeg stdout."""
        while self._running and self._proc and self._proc.stdout:
            try:
                # Read chunks of H.264 stream
                chunk = self._proc.stdout.read(8192)
                if not chunk:
                    break
                if self.on_nal_packet:
                    self.on_nal_packet(chunk)
            except Exception as e:
                log.debug("Encoder read exception: %s", e)
                break
        self._running = False

    def stop(self) -> None:
        """Terminate the encoder process."""
        self._running = False
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        log.info("VideoEncoder stopped")
