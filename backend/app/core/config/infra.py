"""Platform database, business database, Redis and local storage."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr, field_validator

from app.core.config.app import resolve_backend_path
from app.core.config.base import (
    BACKEND_DIR,
    ConfigDomain,
    require_non_negative,
    require_positive,
)


class InfraConfig(ConfigDomain):
    storage_dir: Path = BACKEND_DIR / "storage"
    redis_url: str = "redis://127.0.0.1:6379/0"
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "agent_platform"
    database_user: str = "agent_app"
    database_password: SecretStr = SecretStr("")
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout_seconds: int = 5
    business_database_host: str = "business_db"
    business_database_port: int = 5432
    business_database_name: str = "business_data"
    business_database_user: str = "business_readonly"
    business_database_password: SecretStr = SecretStr("")

    @field_validator("storage_dir", mode="before")
    @classmethod
    def infra_resolve_storage_dir(cls, value: str | Path) -> Path:
        return resolve_backend_path(value)

    @field_validator("database_pool_size", "database_pool_timeout_seconds")
    @classmethod
    def infra_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("database_max_overflow")
    @classmethod
    def infra_validate_non_negative_int(cls, value: int) -> int:
        return require_non_negative(value)

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def input_artifact_quarantine_dir(self) -> Path:
        return self.storage_dir / "input-artifacts" / "quarantine"

    @property
    def knowledge_dir(self) -> Path:
        return self.storage_dir / "knowledge"

    @property
    def faiss_dir(self) -> Path:
        return self.storage_dir / "faiss"
