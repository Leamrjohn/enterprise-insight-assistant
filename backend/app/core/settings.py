from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Agent Platform API"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: Path = BACKEND_DIR / "logs"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    storage_dir: Path = BACKEND_DIR / "storage"
    max_upload_size_mb: int = 20
    allowed_document_extensions: list[str] = [".txt", ".pdf", ".md", ".markdown"]
    upload_chunk_size_bytes: int = 1048576
    redis_url: str = "redis://127.0.0.1:6379/0"
    jwt_secret: SecretStr = SecretStr("development-only-change-before-production")
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30

    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "agent_platform"
    database_user: str = "agent_app"
    database_password: SecretStr = SecretStr("")
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    business_database_host: str = "business_db"
    business_database_port: int = 5432
    business_database_name: str = "business_data"
    business_database_user: str = "business_readonly"
    business_database_password: SecretStr = SecretStr("")
    llm_provider: Literal["local", "openai", "deepseek"] = "deepseek"
    llm_model: str = "deepseek-chat"
    openai_api_key: SecretStr | None = None
    llm_timeout_seconds: int = 30
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 1024
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    reranker_model: str = "BAAI/bge-reranker-base"
    rag_retrieval_top_k: int = 10
    rag_retrieval_min_score: float = 0.1
    rag_rerank_top_k: int = 3
    rag_rerank_min_score: float = 0.5

    @model_validator(mode="after")
    def validate_database_password(self) -> Self:
        if not self.database_password.get_secret_value():
            raise ValueError("DATABASE_PASSWORD must not be empty")

        if not self.business_database_password.get_secret_value():
            raise ValueError("BUSINESS_DATABASE_PASSWORD must not be empty")
        if (
            self.app_env == "production"
            and self.jwt_secret.get_secret_value()
            == "development-only-change-before-production"
        ):
            raise ValueError("JWT_SECRET must be configured in production")
        return self

    @field_validator("log_dir", "storage_dir", mode="before")
    @classmethod
    def resolve_backend_path(cls, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (BACKEND_DIR / path).resolve()

    @field_validator(
        "max_upload_size_mb",
        "upload_chunk_size_bytes",
        "rag_retrieval_top_k",
        "rag_rerank_top_k",
    )
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Value must be a positive integer")
        return value

    @field_validator("rag_retrieval_min_score", "rag_rerank_min_score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("Score must be between 0 and 1")
        return value

    @property
    def upload_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def knowledge_dir(self) -> Path:
        return self.storage_dir / "knowledge"

    @property
    def faiss_dir(self) -> Path:
        return self.storage_dir / "faiss"


@lru_cache
def get_settings() -> Settings:
    return Settings()
