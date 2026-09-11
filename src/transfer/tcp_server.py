"""
TCP file transfer server for ScrcpyUltimateLink (PC side).

Listens for incoming connections from the phone and handles:
- ``FILE_SEND``: Receive a file from the phone
- ``FILE_LIST``: Send the list of files in the download directory
- ``FILE_GET``:  Send a requested file to the phone
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.constants import (
    DEFAULT_TCP_TRANSFER_PORT,
    FILE_TRANSFER_TIMEOUT_SEC,
    PROGRESS_UPDATE_INTERVAL_SEC,
    TRANSFER_CHUNK_SIZE,
)
from src.transfer.protocol import (
    build_send_header,
    parse_header,
    parse_send_header,
    parse_get_header,
    sanitize_filename,
    validate_filesize,
    PROTO_FILE_LIST,
    PROTO_FILE_GET,
    PROTO_FILE_SEND,
)
from src.logger import get_logger

log = get_logger(__name__)


class TCPFileServer(QObject):
    """
    TCP server that accepts file transfers from the mobile device.

    Signals
    -------
    file_received(filename, save_path)
        Emitted when a file is successfully received.
    receive_progress(percent, speed_mbps, eta_seconds)
        Emitted during an incoming transfer.
    error(message)
        Emitted on errors.
    """

    file_received = Signal(str, str)   # filename, save_path
    receive_progress = Signal(int, float, float)
    error = Signal(str)

    def __init__(
        self,
        port: int = DEFAULT_TCP_TRANSFER_PORT,
        save_dir: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._port = port
        self._save_dir = save_dir or os.path.expanduser("~/Downloads")
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="TCPServer")

    @property
    def save_dir(self) -> str:
        return self._save_dir

    @save_dir.setter
    def save_dir(self, path: str) -> None:
        self._save_dir = path

    def start(self) -> None:
        """Start the server in a background thread."""
        if self._running:
            return
        self._running = True
        thread = threading.Thread(
            target=self._accept_loop, daemon=True, name="TCPFileServer",
        )
        thread.start()

    def stop(self) -> None:
        """Stop the server gracefully."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        self._pool.shutdown(wait=False)

    def _accept_loop(self) -> None:
        """Main accept loop — dispatches connections to the thread pool."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self._server_sock.bind(("0.0.0.0", self._port))
            self._server_sock.listen(3)
            log.info("TCP file server listening on port %d", self._port)
        except OSError as exc:
            log.error("TCP file server bind failed: %s", exc)
            self.error.emit(f"Server failed to start: {exc}")
            return

        while self._running:
            try:
                conn, addr = self._server_sock.accept()
                self._pool.submit(self._handle_client, conn, addr[0])
            except OSError:
                if self._running:
                    time.sleep(1)

        log.info("TCP file server stopped")

    def _handle_client(self, conn: socket.socket, client_ip: str) -> None:
        """Handle a single client connection."""
        try:
            conn.settimeout(FILE_TRANSFER_TIMEOUT_SEC)
            header_line = self._read_line(conn)

            if not header_line:
                return

            command, args = parse_header(header_line)

            if command == PROTO_FILE_LIST:
                self._handle_list(conn)
            elif command == PROTO_FILE_GET:
                self._handle_get(conn, args)
            elif command == PROTO_FILE_SEND:
                self._handle_receive(conn, args, client_ip)
            else:
                log.warning("Unknown protocol command from %s: %s", client_ip, command)

        except (OSError, ValueError) as exc:
            log.debug("Client handler error (%s): %s", client_ip, exc)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _handle_list(self, conn: socket.socket) -> None:
        """Send the list of files in the save directory."""
        os.makedirs(self._save_dir, exist_ok=True)
        files = []
        try:
            for name in sorted(os.listdir(self._save_dir)):
                path = os.path.join(self._save_dir, name)
                if os.path.isfile(path):
                    files.append({"name": name, "size": os.path.getsize(path)})
        except OSError as exc:
            log.warning("Failed to list files: %s", exc)

        response = json.dumps(files) + "\n"
        conn.sendall(response.encode("utf-8"))

    def _handle_get(self, conn: socket.socket, args: list[str]) -> None:
        """Send a requested file to the client."""
        if not args:
            return

        filename = sanitize_filename(args[0])
        filepath = os.path.join(self._save_dir, filename)

        if not os.path.isfile(filepath):
            log.warning("Requested file not found: %s", filename)
            return

        filesize = os.path.getsize(filepath)
        header = build_send_header(filename, filesize)
        conn.sendall(header)

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(TRANSFER_CHUNK_SIZE)
                if not chunk:
                    break
                conn.sendall(chunk)

        log.info("Served file: %s (%d bytes)", filename, filesize)

    def _handle_receive(
        self, conn: socket.socket, args: list[str], client_ip: str,
    ) -> None:
        """Receive a file from the client."""
        if len(args) < 2:
            log.warning("Invalid FILE_SEND header from %s", client_ip)
            return

        filename = sanitize_filename(args[0])
        try:
            filesize = int(args[1])
        except ValueError:
            log.warning("Invalid filesize from %s", client_ip)
            return

        if not validate_filesize(filesize):
            log.warning("Filesize out of bounds from %s: %d", client_ip, filesize)
            return

        # Check disk space
        os.makedirs(self._save_dir, exist_ok=True)
        try:
            free_space = shutil.disk_usage(self._save_dir).free
            if filesize > free_space * 0.95:  # Leave 5% headroom
                msg = f"Insufficient disk space for {filename}"
                log.error(msg)
                self.error.emit(msg)
                return
        except OSError:
            pass  # Can't check — proceed anyway

        filepath = os.path.join(self._save_dir, filename)
        log.info("Receiving '%s' (%d bytes) from %s", filename, filesize, client_ip)

        received = 0
        start_time = time.perf_counter()
        last_update = start_time
        last_bytes = 0

        try:
            with open(filepath, "wb") as f:
                while received < filesize:
                    to_read = min(TRANSFER_CHUNK_SIZE, filesize - received)
                    chunk = conn.recv(to_read)
                    if not chunk:
                        raise ConnectionError("Client disconnected")
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
                        self.receive_progress.emit(percent, speed, eta)
                        last_bytes = received
                        last_update = now

            self.receive_progress.emit(100, 0, 0)
            elapsed = time.perf_counter() - start_time
            log.info(
                "File received: %s (%d bytes) in %.1fs", filename, filesize, elapsed,
            )
            self.file_received.emit(filename, filepath)

        except (ConnectionError, OSError) as exc:
            log.error("File receive failed: %s", exc)
            self.error.emit(f"Receive failed: {exc}")
            # Clean up partial file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _read_line(sock: socket.socket, max_bytes: int = 4096) -> str:
        """Read bytes from socket until newline."""
        buf = bytearray()
        while len(buf) < max_bytes:
            byte = sock.recv(1)
            if not byte:
                break
            if byte == b"\n":
                break
            buf.extend(byte)
        return buf.decode("utf-8", errors="ignore").strip()
