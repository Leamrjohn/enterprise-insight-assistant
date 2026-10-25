"""ClamAV daemon adapter. It returns a scan fact and never mutates database state."""

import socket
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ScanDisposition = Literal["clean", "rejected", "failed"]
_CHUNK_SIZE = 1024 * 1024
_MAX_REPLY_BYTES = 16 * 1024


class ClamDProtocolError(RuntimeError):
    """clamd returned a reply that cannot be trusted as a scan result."""


@dataclass(frozen=True, slots=True)
class ScanResult:
    disposition: ScanDisposition
    reason_code: str | None = None


class ClamDScanner:
    """Stream one local file to a private clamd TCP endpoint."""

    processor_name = "clamd"

    def __init__(self, *, host: str, port: int, timeout_seconds: int) -> None:
        if not isinstance(host, str) or not host.strip():
            raise ValueError("clamd host is invalid")
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 1 <= port <= 65535
        ):
            raise ValueError("clamd port is invalid")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            raise ValueError("clamd timeout_seconds is invalid")
        self._address = (host.strip(), port)
        self._timeout_seconds = timeout_seconds

    def scan_file(self, path: Path) -> ScanResult:
        if not path.is_file():
            raise ValueError("scan input path must be an existing file")
        try:
            with socket.create_connection(
                self._address,
                timeout=self._timeout_seconds,
            ) as connection:
                connection.settimeout(self._timeout_seconds)
                connection.sendall(b"zINSTREAM\0")
                with path.open("rb") as source:
                    while chunk := source.read(_CHUNK_SIZE):
                        connection.sendall(struct.pack("!I", len(chunk)))
                        connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                reply = _read_clamd_reply(connection)
        except TimeoutError:
            return ScanResult("failed", "scanner_timeout")
        except ClamDProtocolError:
            return ScanResult("failed", "scanner_protocol_error")
        except OSError:
            return ScanResult("failed", "scanner_unavailable")

        if reply.endswith(": OK"):
            return ScanResult("clean")
        if reply.endswith(" FOUND"):
            return ScanResult("rejected", "malware_detected")
        return ScanResult("failed", "scanner_protocol_error")


def _read_clamd_reply(connection: socket.socket) -> str:
    received = bytearray()
    while len(received) < _MAX_REPLY_BYTES:
        chunk = connection.recv(min(4096, _MAX_REPLY_BYTES - len(received)))
        if not chunk:
            break
        received.extend(chunk)
        if b"\0" in chunk:
            break
    reply, separator, _ = bytes(received).partition(b"\0")
    if not separator:
        raise ClamDProtocolError("clamd closed without a terminated reply")
    try:
        return reply.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ClamDProtocolError("clamd returned a non-UTF-8 reply") from exc
