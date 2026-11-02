import errno

import pytest
from app.core.exceptions import PermanentModelError, RetryableModelError
from app.modules.workflow.tasks import _is_retryable_exception, _retry_countdown


@pytest.mark.parametrize(
    "exc",
    [
        ConnectionError("broker reset"),
        TimeoutError("provider timeout"),
        RetryableModelError("429"),
        OSError(errno.ECONNRESET, "reset"),
    ],
)
def test_transient_failures_are_retried(exc: Exception) -> None:
    assert _is_retryable_exception(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        PermissionError("read-only mount"),
        FileNotFoundError("missing model file"),
        IsADirectoryError("path is a directory"),
        OSError(errno.ENOSPC, "disk full"),
        PermanentModelError("invalid api key"),
        ValueError("contract violation"),
    ],
)
def test_permanent_failures_are_not_retried(exc: Exception) -> None:
    assert _is_retryable_exception(exc) is False


def test_retry_countdown_grows_exponentially_with_bounded_jitter() -> None:
    low = [_retry_countdown(n, random=lambda: 0.0) for n in range(3)]
    high = [_retry_countdown(n, random=lambda: 1.0) for n in range(3)]

    assert low == [1.0, 2.0, 4.0]
    assert high == [3.0, 6.0, 12.0]


def test_retry_countdown_spreads_simultaneous_failures() -> None:
    delays = {round(_retry_countdown(0), 3) for _ in range(20)}

    assert len(delays) > 1
