from pathlib import Path

from app.modules.input_artifacts.processing.scanner import ClamDScanner


class _FakeSocket:
    def __init__(self, reply: bytes) -> None:
        self.reply = reply
        self.sent: list[bytes] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def settimeout(self, _timeout: int) -> None:
        return None

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, _size: int) -> bytes:
        reply, self.reply = self.reply, b""
        return reply


def test_clamd_scanner_streams_file_and_accepts_a_clean_reply(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "input.txt"
    source.write_bytes(b"safe content")
    connection = _FakeSocket(b"stream: OK\0")
    monkeypatch.setattr(
        "app.modules.input_artifacts.processing.scanner.socket.create_connection",
        lambda *_args, **_kwargs: connection,
    )

    result = ClamDScanner(host="clamd", port=3310, timeout_seconds=10).scan_file(source)

    assert result.disposition == "clean"
    assert result.reason_code is None
    assert connection.sent[0] == b"zINSTREAM\0"
    assert connection.sent[-1] == b"\x00\x00\x00\x00"


def test_clamd_scanner_maps_a_detection_to_rejected(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "input.bin"
    source.write_bytes(b"eicar")
    connection = _FakeSocket(b"stream: Win.Test.EICAR_HDB-1 FOUND\0")
    monkeypatch.setattr(
        "app.modules.input_artifacts.processing.scanner.socket.create_connection",
        lambda *_args, **_kwargs: connection,
    )

    result = ClamDScanner(host="clamd", port=3310, timeout_seconds=10).scan_file(source)

    assert result.disposition == "rejected"
    assert result.reason_code == "malware_detected"


def test_clamd_scanner_maps_connection_failure_to_retryable_failure(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "input.bin"
    source.write_bytes(b"safe")
    monkeypatch.setattr(
        "app.modules.input_artifacts.processing.scanner.socket.create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()),
    )

    result = ClamDScanner(host="clamd", port=3310, timeout_seconds=10).scan_file(source)

    assert result.disposition == "failed"
    assert result.reason_code == "scanner_unavailable"


def test_clamd_scanner_maps_an_unterminated_reply_to_protocol_failure(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "input.bin"
    source.write_bytes(b"safe")
    connection = _FakeSocket(b"stream: unknown")
    monkeypatch.setattr(
        "app.modules.input_artifacts.processing.scanner.socket.create_connection",
        lambda *_args, **_kwargs: connection,
    )

    result = ClamDScanner(host="clamd", port=3310, timeout_seconds=10).scan_file(source)

    assert result.disposition == "failed"
    assert result.reason_code == "scanner_protocol_error"
