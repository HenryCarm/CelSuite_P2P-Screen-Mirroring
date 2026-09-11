"""
Fast concurrent subnet scanner for ScrcpyUltimateLink.

Uses a ``ThreadPoolExecutor`` to probe the local /24 subnet for
devices with an open ADB port, with early termination once a device
is found.
"""

from __future__ import annotations

import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.config import AppConfig
from src.constants import (
    DEFAULT_ADB_PORT,
    SCANNER_MAX_WORKERS,
    SUBNET_SCAN_TIMEOUT_SEC,
)
from src.networking.heartbeat import get_local_ip
from src.logger import get_logger

log = get_logger(__name__)


class SubnetScanner(QObject):
    """
    Scans the local /24 subnet for devices with open ADB ports.

    Signals
    -------
    device_found(ip)
        Emitted when a device with an open ADB port is found.
    scan_progress(current, total)
        Emitted to report scan progress.
    scan_complete(found_ip_or_none)
        Emitted when the scan finishes. ``None`` if no device found.
    """

    device_found = Signal(str)
    scan_progress = Signal(int, int)  # current, total
    scan_complete = Signal(object)    # str or None

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._scanning = False
        self._cancel_event = threading.Event()

    @property
    def is_scanning(self) -> bool:
        return self._scanning

    def start_scan(self) -> None:
        """Launch the scan in a background thread."""
        if self._scanning:
            return
        self._scanning = True
        self._cancel_event.clear()
        thread = threading.Thread(
            target=self._scan, daemon=True, name="SubnetScanner",
        )
        thread.start()

    def cancel(self) -> None:
        """Cancel a running scan."""
        self._cancel_event.set()

    def _scan(self) -> None:
        """Perform the subnet scan."""
        local_ip = get_local_ip()
        if "unknown" in local_ip:
            log.warning("Cannot scan — local IP unknown")
            self._scanning = False
            self.scan_complete.emit(None)
            return

        parts = local_ip.split(".")
        if len(parts) != 4:
            self._scanning = False
            self.scan_complete.emit(None)
            return

        base = f"{parts[0]}.{parts[1]}.{parts[2]}."
        adb_port = self._config.get("adb_port", DEFAULT_ADB_PORT)
        total = 254
        found_ip: Optional[str] = None
        found_event = threading.Event()

        log.info(
            "Starting subnet scan: %s1-%s254 on port %d",
            base, base, adb_port,
        )

        def probe(ip: str) -> Optional[str]:
            """Try to connect to ADB port on a single IP."""
            if found_event.is_set() or self._cancel_event.is_set():
                return None
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(SUBNET_SCAN_TIMEOUT_SEC)
                s.connect((ip, adb_port))
                s.close()
                return ip
            except (OSError, socket.timeout):
                return None

        # Step 1: Instant Gateway check (for Mobile Hotspot where phone is the default gateway)
        try:
            import subprocess
            gw_res = subprocess.run(["ip", "route"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in gw_res.stdout.splitlines():
                if line.startswith("default via"):
                    gw_ip = line.split()[2]
                    if gw_ip.startswith(base) and probe(gw_ip):
                        found_ip = gw_ip
                        found_event.set()
                        log.info("Subnet scanner instantly found Hotspot Phone at gateway %s", found_ip)
                        self.device_found.emit(found_ip)
                        self._scanning = False
                        self.scan_complete.emit(found_ip)
                        return
        except Exception as e:
            log.debug("Gateway check skipped: %s", e)

        scanned = 0
        with ThreadPoolExecutor(max_workers=SCANNER_MAX_WORKERS) as pool:
            # Skip our own IP
            targets = [
                base + str(i) for i in range(1, 255)
                if base + str(i) != local_ip
            ]

            futures = {pool.submit(probe, ip): ip for ip in targets}

            for future in as_completed(futures):
                if self._cancel_event.is_set():
                    break

                scanned += 1
                result = future.result()

                try:
                    if result is not None and found_ip is None:
                        found_ip = result
                        found_event.set()  # Signal other threads to stop
                        log.info("Subnet scanner found device at %s", found_ip)
                        self.device_found.emit(found_ip)

                    # Report progress every 10 hosts
                    if scanned % 10 == 0:
                        self.scan_progress.emit(scanned, total)
                except RuntimeError:
                    break

        self._scanning = False
        try:
            self.scan_complete.emit(found_ip)
        except RuntimeError:
            pass

        if found_ip:
            log.info("Subnet scan complete — found: %s", found_ip)
        else:
            log.info("Subnet scan complete — no devices found")
