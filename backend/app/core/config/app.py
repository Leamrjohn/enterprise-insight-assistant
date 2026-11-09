"""Application identity, environment, logging and CORS."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from app.core.config.base import BACKEND_DIR, ConfigDomain


class AppConfig(ConfigDomain):
    app_name: str = "Agent Platform API"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: Path = BACKEND_DIR / "logs"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    workflow_release_version: Literal["v1", "v2-candidate"] = "v1"

    @field_validator("log_dir", mode="before")
    @classmethod
    def app_resolve_log_dir(cls, value: str | Path) -> Path:
        return resolve_backend_path(value)


def resolve_backend_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (BACKEND_DIR / path).resolve()
