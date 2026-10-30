"""
TCP file transfer client for ScrcpyUltimateLink.

Handles sending files to the phone and pulling files from the phone,
with progress reporting, ETA calculation, and cancellation support.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.constants import (
    DEFAULT_TCP_TRANSFER_PORT,
    FILE_TRANSFER_TIMEOUT_SEC,
    PROGRESS_UPDATE_INTERVAL_SEC,
    TRANSFER_CHUNK_SIZE,
)
from src.transfer.protocol import (
    build_get_request,
    build_list_request,
    build_send_header,
    parse_send_header,
    sanitize_filename,
)
from src.logger import get_logger

log = get_logger(__name__)


class TCPFileClient(QObject):
    """
    Client for sending/receiving files over WiFi via the custom TCP protocol.

    Signals
    -------
    progress_updated(percent, speed_mbps, eta_seconds)
        Emitted periodically during transfer.
    transfer_finished(success, message)
        Emitted when a transfer completes or fails.
    file_list_ready(files)
        Emitted when the remote file list is received.
    """

    progress_updated = Signal(int, float, float)
    transfer_finished = Signal(bool, str)
    file_list_ready = Signal(list)

    def __init__(self, port: int = DEFAULT_TCP_TRANSFER_PORT) -> None:
        super().__init__()
        self._port = port
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Cancel the current transfer."""
        self._cancel_event.set()

    def send_file(self, local_path: str, device_ip: str) -> None:
        """Send a file to the phone in a background thread."""
        if not os.path.isfile(local_path):
            self.transfer_finished.emit(False, "Local file not found.")
            return

        self._cancel_event.clear()
        thread = threading.Thread(
            target=self._send_worker, args=(local_path, device_ip),
            daemon=True, name="FileSendWorker",
        )
        thread.start()

    def request_file_list(self, device_ip: str) -> None:
        """Request the remote file list in a background thread."""
        thread = threading.Thread(
            target=self._list_worker, args=(device_ip,),
            daemon=True, name="FileListWorker",
        )
        thread.start()

    def pull_file(
        self, remote_filename: str, device_ip: str, local_save_path: str,
    ) -> None:
        """Download a file from the phone in a background thread."""
        self._cancel_event.clear()
        thread = threading.Thread(
            target=self._pull_worker,
            args=(remote_filename, device_ip, local_save_path),
            daemon=True, name="FilePullWorker",
        )
        thread.start()

    # ── Workers ───────────────────────────────────────────────────────────

    def _send_worker(self, local_path: str, device_ip: str) -> None:
        """Send a file to the device's TCP server."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(FILE_TRANSFER_TIMEOUT_SEC)

        try:
            sock.connect((device_ip, self._port))
            filesize = os.path.getsize(local_path)
            filename = os.path.basename(local_path)

            # Send protocol header
            header = build_send_header(filename, filesize)
            sock.sendall(header)

            # Stream file data
            sent = 0
            start_time = time.perf_counter()
            last_update = start_time
            last_bytes = 0

            with open(local_path, "rb") as f:
                while sent < filesize:
                    if self._cancel_event.is_set():
                        self.transfer_finished.emit(False, "Transfer cancelled.")
                        return

                    chunk = f.read(TRANSFER_CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    sent += len(chunk)

                    # Progress updates
                    now = time.perf_counter()
                    if now - last_update >= PROGRESS_UPDATE_INTERVAL_SEC:
                        dt = now - last_update
                        delta = sent - last_bytes
                        speed = (delta / dt) / (1024 * 1024) if dt > 0 else 0
                        percent = int((sent / filesize) * 100) if filesize > 0 else 100
                        remaining = filesize - sent
                        eta = remaining / (delta / dt) if delta > 0 and dt > 0 else 0
                        self.progress_updated.emit(percent, speed, eta)
                        last_bytes = sent
                        last_update = now

            self.progress_updated.emit(100, 0, 0)
            elapsed = time.perf_counter() - start_time
            avg_speed = (filesize / elapsed) / (1024 * 1024) if elapsed > 0 else 0
            self.transfer_finished.emit(
                True,
                f"Sent '{filename}' ({filesize / (1024*1024):.1f} MB) "
                f"in {elapsed:.1f}s ({avg_speed:.1f} MB/s)",
            )
            log.info("File sent: %s (%d bytes) in %.1fs", filename, filesize, elapsed)

        except ConnectionRefusedError:
            self.transfer_finished.emit(
                False, "Connection refused — is the phone's TCP server running?",
            )
        except socket.timeout:
            self.transfer_finished.emit(False, "Connection timed out.")
        except OSError as exc:
            self.transfer_finished.emit(False, f"Network error: {exc}")
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _list_worker(self, device_ip: str) -> None:
        """Request the file list from the device."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(FILE_TRANSFER_TIMEOUT_SEC)

        try:
            sock.connect((device_ip, self._port))
            sock.sendall(build_list_request())

            # Read complete response
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)

            raw = b"".join(chunks).decode("utf-8", errors="ignore").strip()
            data = json.loads(raw) if raw else []
            self.file_list_ready.emit(data)
            log.debug("Received file list: %d items", len(data))

        except (json.JSONDecodeError, ConnectionRefusedError, socket.timeout, OSError) as exc:
            log.warning("File list request failed: %s", exc)
            self.file_list_ready.emit([])
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _pull_worker(
        self, remote_filename: str, device_ip: str, local_save_path: str,
    ) -> None:
        """Download a file from the device."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(FILE_TRANSFER_TIMEOUT_SEC)

        try:
            sock.connect((device_ip, self._port))
            sock.sendall(build_get_request(remote_filename))

            # Read response header (line-buffered)
            header_buf = self._read_line(sock)
            if not header_buf:
                raise ConnectionError("No response from server")

            filename, filesize = parse_send_header(header_buf)
            if filename is None or filesize is None:
                raise ValueError(f"Invalid server response: {header_buf!r}")

            # Receive file data
            received = 0
            start_time = time.perf_counter()
            last_update = start_time
            last_bytes = 0

            with open(local_save_path, "wb") as f:
                while received < filesize:
                    if self._cancel_event.is_set():
                        self.transfer_finished.emit(False, "Download cancelled.")
                        return

                    to_read = min(TRANSFER_CHUNK_SIZE, filesize - received)
                    chunk = sock.recv(to_read)
                    if not chunk:
                        raise ConnectionError("Server disconnected prematurely")
                    f.write(chunk)
                    received += len(chunk)

                    now = time.perf_counter()
                    if now - last_update >= PROGRESS_UPDATE_INTERVAL_SEC:
                        dt = now - last_update
                        delta = received - last_bytes
                        speed = (delta / dt) / (1024 * 1024) if dt > 0 else 0
                        percent = int((received / filesize) * 100) if filesize > 0 else 100
                        remaining = filesize - received
                        eta = remaining / (delta / dt) if delta > 0 and dt > 0 else 0
                        self.progress_updated.emit(percent, speed, eta)
                        last_bytes = received
                        last_update = now

            self.progress_updated.emit(100, 0, 0)
            elapsed = time.perf_counter() - start_time
            avg_speed = (filesize / elapsed) / (1024 * 1024) if elapsed > 0 else 0
            self.transfer_finished.emit(
                True,
                f"Downloaded '{remote_filename}' ({filesize / (1024*1024):.1f} MB) "
                f"in {elapsed:.1f}s ({avg_speed:.1f} MB/s)",
            )

        except (ConnectionRefusedError, ConnectionError, socket.timeout, OSError, ValueError) as exc:
            self.transfer_finished.emit(False, f"Download failed: {exc}")
            # Clean up partial file
            try:
                if os.path.exists(local_save_path):
                    os.remove(local_save_path)
            except OSError:
                pass
        finally:
            try:
                sock.close()
            except OSError:
                pass

    @staticmethod
    def _read_line(sock: socket.socket, max_bytes: int = 4096) -> str:
        """Read bytes until newline, using buffered approach."""
        buf = bytearray()
        while len(buf) < max_bytes:
            byte = sock.recv(1)
            if not byte:
                break
            if byte == b"\n":
                break
            buf.extend(byte)
        return buf.decode("utf-8", errors="ignore").strip()
