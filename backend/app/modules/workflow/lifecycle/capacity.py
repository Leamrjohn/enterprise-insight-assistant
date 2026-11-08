"""Fail-closed capacity admission from an authenticated local volume signal."""

import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.exceptions import (
    TaskCapacityLowWatermarkError,
    TaskCapacitySignalUnavailableError,
)
from app.core.settings import Settings

_SIGNAL_SCHEMA_VERSION = "capacity-signal/v1"
_MAX_SIGNAL_BYTES = 4096
_SIGNATURE_HEADER = "X-Capacity-Signal-Signature"


def require_task_capacity(settings: Settings) -> None:
    """Reject new work if the configured persistent-volume signal is unsafe."""
    if not settings.analysis_task_capacity_admission_enabled:
        return

    try:
        payload = _read_capacity_signal(settings)
        available_bytes = _validated_available_bytes(payload, settings=settings)
    except TaskCapacityLowWatermarkError:
        raise
    except Exception as exc:
        raise TaskCapacitySignalUnavailableError(
            retry_after_seconds=settings.analysis_task_admission_retry_after_seconds
        ) from exc

    if available_bytes < settings.analysis_task_capacity_low_watermark_bytes:
        raise TaskCapacityLowWatermarkError(
            retry_after_seconds=settings.analysis_task_admission_retry_after_seconds
        )


def _read_capacity_signal(settings: Settings) -> dict[str, object]:
    token = settings.analysis_task_capacity_signal_token
    if token is None or settings.analysis_task_capacity_signal_url is None:
        raise ValueError("capacity signal settings are incomplete")
    request = Request(
        settings.analysis_task_capacity_signal_url,
        headers={
            "Accept": "application/json",
            "X-Capacity-Signal-Token": token.get_secret_value(),
            "Cache-Control": "no-store",
        },
    )
    try:
        with urlopen(
            request,
            timeout=settings.analysis_task_capacity_signal_timeout_seconds,
        ) as response:
            if response.status != 200:
                raise ValueError("capacity signal returned a non-success status")
            body = response.read(_MAX_SIGNAL_BYTES + 1)
            signature = response.headers.get(_SIGNATURE_HEADER)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError("capacity signal request failed") from exc
    if len(body) > _MAX_SIGNAL_BYTES:
        raise ValueError("capacity signal response is too large")
    expected_signature = hmac.new(
        token.get_secret_value().encode(), body, sha256
    ).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, expected_signature
    ):
        raise ValueError("capacity signal response signature is invalid")
    try:
        payload = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise ValueError("capacity signal response is not JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("capacity signal response must be an object")
    return payload


def _validated_available_bytes(
    payload: dict[str, object], *, settings: Settings
) -> int:
    if payload.get("schema_version") != _SIGNAL_SCHEMA_VERSION:
        raise ValueError("capacity signal schema version is unsupported")
    available_bytes = payload.get("available_bytes")
    total_bytes = payload.get("total_bytes")
    observed_at = payload.get("observed_at")
    if (
        isinstance(available_bytes, bool)
        or not isinstance(available_bytes, int)
        or available_bytes < 0
        or isinstance(total_bytes, bool)
        or not isinstance(total_bytes, int)
        or total_bytes <= 0
        or available_bytes > total_bytes
        or not isinstance(observed_at, str)
    ):
        raise ValueError("capacity signal values are invalid")
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("capacity signal observed_at is invalid") from exc
    if observed.tzinfo is None:
        raise ValueError("capacity signal observed_at must include a timezone")
    age_seconds = (datetime.now(UTC) - observed.astimezone(UTC)).total_seconds()
    if (
        age_seconds < -1
        or age_seconds > settings.analysis_task_capacity_signal_max_age_seconds
    ):
        raise ValueError("capacity signal is stale")
    return available_bytes
