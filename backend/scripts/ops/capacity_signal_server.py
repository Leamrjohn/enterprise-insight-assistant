"""Expose a read-only PostgreSQL-volume capacity signal on the Compose network."""

import hmac
import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_SIGNAL_PATH = "/v1/postgres-volume"
_HEALTH_PATH = "/health/live"
_TOKEN_HEADER = "X-Capacity-Signal-Token"
_SCHEMA_VERSION = "capacity-signal/v1"
_SIGNATURE_HEADER = "X-Capacity-Signal-Signature"


def _capacity_payload(root: Path) -> dict[str, object]:
    stats = os.statvfs(root)
    block_size = stats.f_frsize
    return {
        "schema_version": _SCHEMA_VERSION,
        "observed_at": datetime.now(UTC).isoformat(),
        "available_bytes": stats.f_bavail * block_size,
        "total_bytes": stats.f_blocks * block_size,
    }


def _response_signature(token: str, body: bytes) -> str:
    return hmac.new(token.encode(), body, sha256).hexdigest()


class CapacitySignalHandler(BaseHTTPRequestHandler):
    token = ""
    root = Path("/")

    def do_GET(self) -> None:
        if self.path == _HEALTH_PATH:
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if self.path != _SIGNAL_PATH:
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": "not found"})
            return
        supplied_token = self.headers.get(_TOKEN_HEADER, "")
        if not hmac.compare_digest(supplied_token, self.token):
            self._write_json(HTTPStatus.FORBIDDEN, {"detail": "forbidden"})
            return
        try:
            self._write_json(HTTPStatus.OK, _capacity_payload(self.root))
        except OSError:
            self._write_json(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": "unavailable"})

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if self.path == _SIGNAL_PATH:
            self.send_header(_SIGNATURE_HEADER, _response_signature(self.token, body))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    token = os.environ.get("CAPACITY_SIGNAL_TOKEN", "")
    if not token:
        raise RuntimeError("CAPACITY_SIGNAL_TOKEN must not be empty")
    root = Path(os.environ.get("CAPACITY_SIGNAL_ROOT", "/var/lib/postgresql/data"))
    CapacitySignalHandler.token = token
    CapacitySignalHandler.root = root
    server = ThreadingHTTPServer(("0.0.0.0", 8081), CapacitySignalHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
