import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from app.core.settings import Settings

request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-",
)
_logging_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(
                record,
                "request_id",
                request_id_context.get(),
            ),
        }

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

        # ── 敏感信息脱敏 ──────────────────────
        for key, value in payload.items():
            if isinstance(value, str):
                if value.startswith("sk-"):
                    payload[key] = "***"
                elif key == "sql" and len(value) > 200:
                    payload[key] = value[:200] + "..."

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    global _logging_configured

    settings.log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    if _logging_configured:
        return

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )

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
