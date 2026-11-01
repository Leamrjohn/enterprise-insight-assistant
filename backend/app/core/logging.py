import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.core.redaction import redact_text
from app.core.settings import Settings

request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-",
)
# Set by the Worker for one claimed execution; None outside task scope.
task_id_context: ContextVar[int | None] = ContextVar("task_id", default=None)
execution_attempt_id_context: ContextVar[int | None] = ContextVar(
    "execution_attempt_id", default=None
)
_logging_configured = False


def _component(logger_name: str) -> str:
    """app.modules.<component>.… → <component>; other loggers keep their root."""
    parts = logger_name.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "modules"]:
        return parts[2]
    return parts[0]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "component": _component(record.name),
            "message": record.getMessage(),
            "request_id": getattr(
                record,
                "request_id",
                request_id_context.get(),
            ),
        }
        for field, context in (
            ("task_id", task_id_context),
            ("execution_attempt_id", execution_attempt_id_context),
        ):
            value = getattr(record, field, context.get())
            if value is not None:
                payload[field] = value

        for field in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "attempt",
            "max_attempts",
            "next_attempt",
            "delay_seconds",
            "error_type",
            "is_graph_repair",
            "error_code",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # ── 敏感信息脱敏：消息、异常堆栈和附加字段一视同仁 ──────────────────────
        for key, value in payload.items():
            if isinstance(value, str):
                value = redact_text(value)
                if key == "sql" and len(value) > 200:
                    value = value[:200] + "..."
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False)


def build_console_formatter() -> logging.Formatter:
    """Container stdout uses the same redacted one-line JSON as the log file."""
    return JsonFormatter()


def configure_logging(settings: Settings) -> None:
    global _logging_configured

    settings.log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    if _logging_configured:
        return

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(build_console_formatter())

    file_handler = RotatingFileHandler(
        filename=settings.log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    _logging_configured = True
