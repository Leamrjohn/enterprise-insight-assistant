import hmac
from hashlib import sha256
from types import SimpleNamespace

from scripts import capacity_signal_server


def test_capacity_payload_reports_only_live_filesystem_measurements(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        capacity_signal_server.os,
        "statvfs",
        lambda _path: SimpleNamespace(f_bavail=25, f_blocks=100, f_frsize=4096),
        raising=False,
    )

    payload = capacity_signal_server._capacity_payload(tmp_path)

    assert payload["schema_version"] == "capacity-signal/v1"
    assert isinstance(payload["observed_at"], str)
    assert isinstance(payload["available_bytes"], int)
    assert isinstance(payload["total_bytes"], int)
    assert payload["available_bytes"] == 102_400
    assert payload["total_bytes"] == 409_600
    assert set(payload) == {
        "schema_version",
        "observed_at",
        "available_bytes",
        "total_bytes",
    }


def test_capacity_signal_signature_uses_the_exact_response_body() -> None:
    body = b'{"available_bytes":1}'
    signature = capacity_signal_server._response_signature("test-token", body)

    assert hmac.compare_digest(
        signature,
        hmac.new(b"test-token", body, sha256).hexdigest(),
    )
