"""
Heartbeat and discovery networking for ScrcpyUltimateLink.

The heartbeat protocol works as follows:

1. PC broadcasts ``SCRCPC_HERE <ip> <port>`` via UDP on the discovery port.
2. Phone receives the broadcast and starts sending ``HELLO_USER|<ip>|<port>``
   heartbeats to the PC's heartbeat port.
3. PC receives the heartbeat and connects via ADB + launches scrcpy.
"""

from __future__ import annotations

import socket
import time
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.constants import (
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_HEARTBEAT_PORT,
    DEFAULT_ADB_PORT,
    DISCOVERY_INTERVAL_SEC,
    HEARTBEAT_DEBOUNCE_SEC,
    PROTO_DISCOVERY_PREFIX,
    PROTO_HEARTBEAT_PREFIX,
    PROTO_CLIPBOARD_PREFIX,
    UDP_LISTEN_TIMEOUT_SEC,
    ConnectionState,
)
from src.config import AppConfig
from src.logger import get_logger

log = get_logger(__name__)


# ── Discovery Broadcaster ────────────────────────────────────────────────────

class DiscoveryBroadcaster:
    """
    Broadcasts the PC's presence via UDP so phones can discover it.

    Sends to both 255.255.255.255 (global broadcast) and the subnet-specific
    broadcast address for better compatibility across network configurations.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start broadcasting in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._broadcast_loop, daemon=True, name="DiscoveryBroadcaster",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop broadcasting and release the socket."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _broadcast_loop(self) -> None:
        """Main broadcast loop — sends discovery packets every few seconds."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        local_ip = _get_local_ip()
        port = self._config.get("discovery_port", DEFAULT_DISCOVERY_PORT)
        hb_port = self._config.get("heartbeat_port", DEFAULT_HEARTBEAT_PORT)
        message = f"{PROTO_DISCOVERY_PREFIX} {local_ip} {hb_port}".encode("utf-8")

        log.info(
            "Discovery broadcaster starting on port %d (PC IP: %s)", port, local_ip,
        )

        while self._running:
            try:
                # Global broadcast
                self._sock.sendto(message, ("255.255.255.255", port))

                # Subnet-specific broadcast
                subnet_bcast = _get_subnet_broadcast(local_ip)
                if subnet_bcast:
                    self._sock.sendto(message, (subnet_bcast, port))

            except OSError as exc:
                log.debug("Broadcast send error: %s", exc)

            time.sleep(DISCOVERY_INTERVAL_SEC)

        # Cleanup
        try:
            self._sock.close()
        except OSError:
            pass
        self._sock = None
        log.info("Discovery broadcaster stopped")


# ── Heartbeat Listener ────────────────────────────────────────────────────────

class HeartbeatListener(QObject):
    """
    Listens for UDP heartbeat packets from the phone.

    Signals
    -------
    heartbeat_received(ip, port)
        Emitted when a valid heartbeat is received. Debounced so it won't
        fire more than once per ``HEARTBEAT_DEBOUNCE_SEC``.
    state_changed(state)
        Emitted when the connection state changes.
    """

    heartbeat_received = Signal(str, int)  # ip, port
    state_changed = Signal(str)
    clipboard_received = Signal(str)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._last_heartbeat_time: float = 0.0
        self._state = ConnectionState.DISCONNECTED

    @property
    def state(self) -> str:
        return self._state

    def start(self) -> None:
        """Start listening in a background thread."""
        if self._running:
            return
        self._running = True
        self._set_state(ConnectionState.DISCOVERING)
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="HeartbeatListener",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop listening and release the socket."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._set_state(ConnectionState.DISCONNECTED)

    def _set_state(self, state: str) -> None:
        """Update connection state and emit signal."""
        if self._state != state:
            self._state = state
            self.state_changed.emit(state)
            log.debug("Connection state: %s", state)

    def _listen_loop(self) -> None:
        """Main listener loop — receives and parses heartbeat packets."""
        port = self._config.get("heartbeat_port", DEFAULT_HEARTBEAT_PORT)

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("0.0.0.0", port))
            self._sock.settimeout(UDP_LISTEN_TIMEOUT_SEC)
            log.info("Heartbeat listener bound to 0.0.0.0:%d", port)
        except OSError as exc:
            log.error("Failed to bind heartbeat port %d: %s", port, exc)
            self._set_state(ConnectionState.ERROR)
            return

        while self._running:
            try:
                data, addr = self._sock.recvfrom(1024)
                message = data.decode("utf-8", errors="ignore").strip()

                if PROTO_HEARTBEAT_PREFIX in message:
                    phone_ip, adb_port = self._parse_heartbeat(message, addr[0])
                    self._handle_heartbeat(phone_ip, adb_port)
                elif PROTO_CLIPBOARD_PREFIX in message:
                    try:
                        _, b64_text = message.split("|", 1)
                        # Wait, the android app sends f"HELLO_CLIPBOARD|{text}"
                        self.clipboard_received.emit(b64_text)
                    except ValueError:
                        pass

            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    log.debug("Heartbeat socket error, retrying...")
                    time.sleep(1)

        # Cleanup
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        self._sock = None
        log.info("Heartbeat listener stopped")

    def _parse_heartbeat(
        self, message: str, sender_ip: str,
    ) -> tuple[str, int]:
        """
        Parse a heartbeat message and extract phone IP + ADB port.

        Expected format: ``HELLO_USER|<phone_ip>|<adb_port>``
        Fallback: use the sender's IP and default ADB port.
        """
        parts = message.split("|")
        if len(parts) >= 3:
            phone_ip = parts[1].strip()
            try:
                adb_port = int(parts[2].strip())
            except ValueError:
                adb_port = self._config.get("adb_port", DEFAULT_ADB_PORT)
        else:
            phone_ip = sender_ip
            adb_port = self._config.get("adb_port", DEFAULT_ADB_PORT)

        return phone_ip, adb_port

    def _handle_heartbeat(self, phone_ip: str, adb_port: int) -> None:
        """
        Handle a received heartbeat — debounced to prevent rapid re-connections.
        """
        now = time.time()
        if now - self._last_heartbeat_time < HEARTBEAT_DEBOUNCE_SEC:
            return

        self._last_heartbeat_time = now
        log.info("Heartbeat received from %s:%d", phone_ip, adb_port)
        self._set_state(ConnectionState.CONNECTING)
        self.heartbeat_received.emit(phone_ip, adb_port)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _get_local_ip() -> str:
    """Get the local IP address with offline/hotspot fallback (Windows & Linux)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    # Offline / Local LAN fallback (crucial for Windows offline or hotspot setups)
    try:
        host_name = socket.gethostname()
        ip = socket.gethostbyname(host_name)
        if ip and not ip.startswith("127."):
            return ip
        for info in socket.getaddrinfo(host_name, None, socket.AF_INET):
            cand = info[4][0]
            if cand and not cand.startswith("127."):
                return cand
    except OSError:
        pass

    return "127.0.0.1"


def _get_subnet_broadcast(ip: str) -> Optional[str]:
    """Derive a /24 subnet broadcast address from an IP."""
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return f"{parts[0]}.{parts[1]}.{parts[2]}.255"
    return None


# Re-export for backward compatibility
get_local_ip = _get_local_ip
