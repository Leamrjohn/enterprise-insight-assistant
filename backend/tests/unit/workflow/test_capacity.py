import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256
from urllib.error import URLError

import pytest
from app.core.exceptions import (
    TaskCapacityLowWatermarkError,
    TaskCapacitySignalUnavailableError,
)
from app.core.settings import get_settings
from app.modules.workflow.lifecycle import capacity
from pydantic import SecretStr


class _Response:
    status = 200

    def __init__(self, payload: dict[str, object], *, signature: str | None) -> None:
        self._body = json.dumps(payload).encode()
        self.headers = {}
        if signature is not None:
            self.headers["X-Capacity-Signal-Signature"] = signature

    def read(self, _size: int) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        return None


def _settings(**updates):
    return get_settings().model_copy(
        update={
            "analysis_task_capacity_admission_enabled": True,
            "analysis_task_capacity_signal_url": "http://capacity-signal/v1/postgres-volume",
            "analysis_task_capacity_signal_token": SecretStr("test-capacity-token"),
            "analysis_task_capacity_low_watermark_bytes": 100,
            "analysis_task_capacity_signal_max_age_seconds": 5,
            "analysis_task_capacity_signal_timeout_seconds": 1,
            **updates,
        }
    )


def _payload(*, available_bytes: int) -> dict[str, object]:
    return {
        "schema_version": "capacity-signal/v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "available_bytes": available_bytes,
        "total_bytes": 1_000,
    }


def _response(payload: dict[str, object], *, signature: str | None = None) -> _Response:
    body = json.dumps(payload).encode()
    return _Response(
        payload,
        signature=(
            signature
            if signature is not None
            else hmac.new(b"test-capacity-token", body, sha256).hexdigest()
        ),
    )


def test_capacity_signal_allows_task_admission_above_low_watermark(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, *, timeout: int):
        captured["token"] = request.get_header("X-capacity-signal-token")
        captured["timeout"] = timeout
        return _response(_payload(available_bytes=100))

    monkeypatch.setattr(capacity, "urlopen", fake_urlopen)

    capacity.require_task_capacity(_settings())

    assert captured == {"token": "test-capacity-token", "timeout": 1}


def test_capacity_signal_rejects_low_watermark(monkeypatch) -> None:
    monkeypatch.setattr(
        capacity,
        "urlopen",
        lambda _request, *, timeout: _response(_payload(available_bytes=99)),
    )

    with pytest.raises(TaskCapacityLowWatermarkError):
        capacity.require_task_capacity(_settings())


def test_capacity_signal_failure_is_fail_closed(monkeypatch) -> None:
    def unavailable(_request, *, timeout: int):
        raise URLError("capacity signal unavailable")

    monkeypatch.setattr(capacity, "urlopen", unavailable)

    with pytest.raises(TaskCapacitySignalUnavailableError):
        capacity.require_task_capacity(_settings())


def test_capacity_signal_rejects_an_unsigned_response(monkeypatch) -> None:
    monkeypatch.setattr(
        capacity,
        "urlopen",
        lambda _request, *, timeout: _Response(
            _payload(available_bytes=100), signature=None
        ),
    )

    with pytest.raises(TaskCapacitySignalUnavailableError):
        capacity.require_task_capacity(_settings())
