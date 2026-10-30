"""
Network latency testing for ScrcpyUltimateLink.

Measures TCP connection latency to the phone's ADB port as a proxy
for overall WiFi link quality.
"""

from __future__ import annotations

import socket
import time
from typing import Optional

from src.constants import (
    DEFAULT_ADB_PORT,
    LATENCY_TEST_TIMEOUT_SEC,
    LATENCY_TEST_ROUNDS,
)
from src.logger import get_logger

log = get_logger(__name__)


def measure_latency(
    phone_ip: str,
    adb_port: int = DEFAULT_ADB_PORT,
    rounds: int = LATENCY_TEST_ROUNDS,
) -> tuple[Optional[float], str]:
    """
    Measure TCP connection latency to the phone.

    Returns ``(avg_ms, description)`` where *avg_ms* is ``None`` on timeout.
    """
    times: list[float] = []

    for _ in range(rounds):
        try:
            start = time.perf_counter()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(LATENCY_TEST_TIMEOUT_SEC)
            s.connect((phone_ip, adb_port))
            s.close()
            latency_ms = (time.perf_counter() - start) * 1000.0
            times.append(latency_ms)
        except (OSError, socket.timeout):
            pass
        time.sleep(0.05)

    if times:
        avg = sum(times) / len(times)
        return avg, f"Ping: {avg:.1f} ms ({len(times)}/{rounds} successful)"

    return None, "Ping: Timeout"
