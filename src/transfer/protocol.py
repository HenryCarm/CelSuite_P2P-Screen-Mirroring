"""
Shared file transfer protocol for ScrcpyUltimateLink.

Provides message builders/parsers and validation used by both the
TCP client and server to ensure consistent encoding.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from src.constants import (
    MAX_FILENAME_LENGTH,
    PROTO_FILE_ACK,
    PROTO_FILE_CANCEL,
    PROTO_FILE_GET,
    PROTO_FILE_LIST,
    PROTO_FILE_SEND,
    PROTO_SEPARATOR,
    PROTO_VERSION,
)

# ── Message Builders ──────────────────────────────────────────────────────────


def build_send_header(filename: str, filesize: int) -> bytes:
    """Build a ``FILE_SEND|filename|filesize`` header."""
    safe_name = sanitize_filename(filename)
    header = f"{PROTO_FILE_SEND}{PROTO_SEPARATOR}{safe_name}{PROTO_SEPARATOR}{filesize}\n"
    return header.encode("utf-8")


def build_list_request() -> bytes:
    """Build a ``FILE_LIST`` request."""
    return f"{PROTO_FILE_LIST}\n".encode("utf-8")


def build_get_request(filename: str) -> bytes:
    """Build a ``FILE_GET|filename`` request."""
    safe_name = sanitize_filename(filename)
    return f"{PROTO_FILE_GET}{PROTO_SEPARATOR}{safe_name}\n".encode("utf-8")


def build_cancel_message() -> bytes:
    """Build a ``FILE_CANCEL`` message."""
    return f"{PROTO_FILE_CANCEL}\n".encode("utf-8")


def build_ack_message(filename: str, success: bool) -> bytes:
    """Build a ``FILE_ACK|filename|ok/fail`` response."""
    status = "ok" if success else "fail"
    return f"{PROTO_FILE_ACK}{PROTO_SEPARATOR}{filename}{PROTO_SEPARATOR}{status}\n".encode("utf-8")


# ── Message Parsers ───────────────────────────────────────────────────────────


def parse_header(raw: str) -> tuple[str, list[str]]:
    """
    Parse a protocol header line into ``(command, parts)``.

    Example::

        >>> parse_header("FILE_SEND|photo.jpg|12345")
        ("FILE_SEND", ["photo.jpg", "12345"])
    """
    parts = raw.strip().split(PROTO_SEPARATOR)
    command = parts[0] if parts else ""
    args = parts[1:] if len(parts) > 1 else []
    return command, args


def parse_send_header(raw: str) -> tuple[Optional[str], Optional[int]]:
    """
    Parse a FILE_SEND header.

    Returns ``(filename, filesize)`` or ``(None, None)`` on invalid input.
    """
    command, args = parse_header(raw)
    if command != PROTO_FILE_SEND or len(args) < 2:
        return None, None
    filename = sanitize_filename(args[0])
    try:
        filesize = int(args[1])
        if filesize < 0:
            return None, None
        return filename, filesize
    except ValueError:
        return None, None


def parse_get_header(raw: str) -> Optional[str]:
    """
    Parse a FILE_GET header.

    Returns the requested filename or ``None`` on invalid input.
    """
    command, args = parse_header(raw)
    if command != PROTO_FILE_GET or not args:
        return None
    return sanitize_filename(args[0])


# ── Validation ────────────────────────────────────────────────────────────────

# Characters not allowed in filenames (Windows, Linux, Android safe)
_UNSAFE_PATTERN = re.compile(r'[/\\:\x00<>"|?*]')


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal and invalid characters.

    - Strips directory components (takes basename only)
    - Removes null bytes, slashes, backslashes, colons
    - Truncates to MAX_FILENAME_LENGTH
    - Returns ``"unnamed"`` if the result is empty
    """
    # Take basename only — strips any directory path
    name = os.path.basename(filename)
    # Remove unsafe characters
    name = _UNSAFE_PATTERN.sub("", name)
    # Strip leading/trailing dots and spaces
    name = name.strip(". ")
    # Truncate
    if len(name) > MAX_FILENAME_LENGTH:
        name = name[:MAX_FILENAME_LENGTH]
    return name or "unnamed"


def validate_filesize(filesize: int, max_bytes: int = 10 * 1024 * 1024 * 1024) -> bool:
    """Check that a filesize is within reasonable bounds (default: 10 GB)."""
    return 0 <= filesize <= max_bytes
