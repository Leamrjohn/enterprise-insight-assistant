import json
import logging

from app.core.logging import JsonFormatter


def test_json_formatter_keeps_planner_retry_observability_fields() -> None:
    record = logging.LogRecord(
        name="app.modules.analysis.planner.planning",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Planner model call failed; waiting before retry",
        args=(),
        exc_info=None,
    )
    record.attempt = 1
    record.next_attempt = 2
    record.delay_seconds = 1.0
    record.error_type = "RetryableModelError"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["attempt"] == 1
    assert payload["next_attempt"] == 2
    assert payload["delay_seconds"] == 1.0
    assert payload["error_type"] == "RetryableModelError"
