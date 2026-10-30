"""
Low-latency Desktop Audio Streamer for CelSuite Reverse Mirror.
Captures system audio output (WASAPI Loopback on Windows / PulseAudio on Linux)
and encodes it into lightweight audio packets to beam to the phone.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from typing import Optional, Callable

from src.logger import get_logger

log = get_logger(__name__)


class AudioStreamer:
    """
    Captures system audio output loopback using ffmpeg and streams packets.
    Includes in-stream mute toggle for instant silence without restarting pipeline.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 2,
        audio_source: str = "default.monitor",
        on_audio_packet: Optional[Callable[[bytes], None]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_source = audio_source
        self.on_audio_packet = on_audio_packet
        self.is_muted = False

        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

    def set_muted(self, muted: bool) -> None:
        """Toggle mute on/off."""
        self.is_muted = muted
        log.info("AudioStreamer mute set to: %s", muted)

    def start(self) -> bool:
        """Start audio capture loopback."""
        if self._running:
            return True

        cmd = [self._ffmpeg_bin, "-y", "-loglevel", "error"]

        if sys.platform == "win32":
            # Windows WASAPI loopback capture fallback
            cmd.extend([
                "-f", "dshow",
                "-i", "audio=virtual-audio-capturer",
            ])
        else:
            # Linux PulseAudio / PipeWire monitor capture (captures speaker/headphone sound)
            cmd.extend([
                "-f", "pulse",
                "-i", self.audio_source,
            ])

        # Output raw 16-bit PCM stereo (lightweight 960 sample chunks = 20ms, 960*2*2 = 3840 B)
        cmd.extend([
            "-ac", str(self.channels),
            "-ar", str(self.sample_rate),
            "-c:a", "pcm_s16le",
            "-f", "s16le",
            "pipe:1",
        ])

        try:
            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "bufsize": 4096,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

            self._proc = subprocess.Popen(cmd, **kwargs)
            self._running = True

            self._reader_thread = threading.Thread(
                target=self._audio_reader_loop, daemon=True, name="AudioStreamerReader"
            )
            self._reader_thread.start()
            log.info("AudioStreamer started (%d Hz, %d channels)", self.sample_rate, self.channels)
            return True
        except Exception as e:
            log.warning("System audio capture could not start (missing virtual device or pulse): %s", e)
            self._running = False
            return False

    def _audio_reader_loop(self) -> None:
        """Reads audio chunks and forwards to callback unless muted."""
        chunk_size = 1920  # ~20ms at 48kHz 16-bit stereo
        while self._running and self._proc and self._proc.stdout:
            try:
                data = self._proc.stdout.read(chunk_size)
                if not data:
                    break
                if not self.is_muted and self.on_audio_packet:
                    self.on_audio_packet(data)
            except Exception as e:
                log.debug("Audio read exception: %s", e)
                break
        self._running = False

    def stop(self) -> None:
        """Stop audio streaming."""
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=0.5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        log.info("AudioStreamer stopped")
