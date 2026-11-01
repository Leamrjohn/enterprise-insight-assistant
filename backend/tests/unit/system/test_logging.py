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


def _record(message: str, *, exc_info=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="app.modules.workflow.tasks",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


def test_json_formatter_carries_task_and_execution_attempt_ids() -> None:
    from app.core.logging import execution_attempt_id_context, task_id_context

    task_token = task_id_context.set(205)
    attempt_token = execution_attempt_id_context.set(31)
    try:
        payload = json.loads(JsonFormatter().format(_record("node finished")))
    finally:
        task_id_context.reset(task_token)
        execution_attempt_id_context.reset(attempt_token)

    assert payload["task_id"] == 205
    assert payload["execution_attempt_id"] == 31
    assert payload["component"] == "workflow"


def test_json_formatter_omits_task_ids_outside_task_scope() -> None:
    payload = json.loads(JsonFormatter().format(_record("api request")))

    assert "task_id" not in payload
    assert "execution_attempt_id" not in payload


def test_json_formatter_redacts_sensitive_text_in_message_and_exception() -> None:
    secrets = [
        "sk-live123456",
        "alice@example.com",
        "+86 138-0013-8000",
        "api_key=abc123",
        "Bearer eyJhbGciOi",
    ]
    message = "call failed: " + " | ".join(secrets)
    try:
        raise RuntimeError("provider said password: hunter2")
    except RuntimeError:
        import sys

        record = _record(message, exc_info=sys.exc_info())

    line = JsonFormatter().format(record)
    payload = json.loads(line)

    for secret in [*secrets, "hunter2"]:
        assert secret not in line
    assert payload["message"].startswith("call failed: ")
    assert "[REDACTED]" in payload["exception"]


def test_console_formatter_is_redacted_json_line() -> None:
    from app.core.logging import build_console_formatter

    line = build_console_formatter().format(_record("token sk-abc999 leaked"))

    assert "\n" not in line
    assert "sk-abc999" not in line
    assert json.loads(line)["level"] == "ERROR"


def test_celery_worker_logging_uses_project_configuration(monkeypatch) -> None:
    import app.core.celery_app as celery_module
    from celery.signals import setup_logging

    calls = []
    monkeypatch.setattr(
        celery_module, "configure_logging", lambda settings: calls.append(settings)
    )

    # Celery skips its own plain-text root handler only when a receiver exists.
    responses = setup_logging.send(
        sender=None, loglevel="INFO", logfile=None, format="", colorize=False
    )

    assert responses
    assert calls == [celery_module.settings]
