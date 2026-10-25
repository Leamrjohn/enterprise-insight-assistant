from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

BACKEND_DIR = Path(__file__).resolve().parents[2]
EXECUTION_LEASE_SECONDS = 120
# A provider call must leave at least half the execution lease for failure and recovery.
MAX_LLM_TIMEOUT_SECONDS = EXECUTION_LEASE_SECONDS // 2
MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS = 5
DEVELOPMENT_CAPACITY_SIGNAL_TOKEN = "local-capacity-signal-development-only"


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
    input_artifact_upload_lease_seconds: int = 120
    input_artifact_direct_upload_ttl_seconds: int = 900
    input_artifact_document_max_size_mb: int = 20
    input_artifact_table_max_size_mb: int = 50
    input_artifact_image_max_size_mb: int = 10
    input_artifact_clamd_host: str = "clamd"
    input_artifact_clamd_port: int = 3310
    input_artifact_clamd_timeout_seconds: int = 30
    input_artifact_clamd_processor_version: str = "1.5.4"
    input_artifact_parser_processor_version: str = "1.0.0"
    input_artifact_ocr_languages: str = "chi_sim+eng"
    input_artifact_ocr_timeout_seconds: int = 30
    input_artifact_image_max_pixels: int = 25_000_000
    input_artifact_ocr_minimum_confidence: float = 60.0
    input_artifact_pdf_render_timeout_seconds: int = 30
    input_artifact_pdf_render_max_side_pixels: int = 2048
    input_artifact_pdf_max_ocr_pages: int = 20
    input_artifact_object_storage_endpoint_url: str | None = None
    input_artifact_object_storage_public_endpoint_url: str | None = None
    input_artifact_object_storage_region: str = "us-east-1"
    input_artifact_object_storage_bucket: str | None = None
    input_artifact_object_storage_access_key_id: SecretStr | None = None
    input_artifact_object_storage_secret_access_key: SecretStr | None = None
    input_artifact_object_storage_health_timeout_seconds: int = 3
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
    database_pool_timeout_seconds: int = 5
    analysis_task_company_inflight_limit: int = 5
    analysis_task_global_inflight_limit: int = 20
    analysis_task_admission_retry_after_seconds: int = 30
    analysis_task_capacity_admission_enabled: bool = False
    analysis_task_capacity_signal_url: str | None = None
    analysis_task_capacity_signal_token: SecretStr | None = None
    analysis_task_capacity_low_watermark_bytes: int = 536_870_912
    analysis_task_capacity_signal_max_age_seconds: int = 5
    analysis_task_capacity_signal_timeout_seconds: int = 1
    business_database_host: str = "business_db"
    business_database_port: int = 5432
    business_database_name: str = "business_data"
    business_database_user: str = "business_readonly"
    business_database_password: SecretStr = SecretStr("")
    llm_provider: Literal["local", "openai", "deepseek"] = "deepseek"
    llm_model: str = "deepseek-chat"
    workflow_release_version: Literal["v1", "v2-candidate"] = "v1"
    openai_api_key: SecretStr | None = None
    llm_timeout_seconds: int = 30
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 1024
    analysis_task_model_max_calls: int = 8
    analysis_task_model_max_calls_per_node: int = 4
    analysis_task_model_max_repairs: int = 2
    analysis_task_model_max_total_tokens: int = 16000
    analysis_task_model_max_cost: Decimal = Decimal("0.15")
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    model_price_table_version: str = "unconfigured"
    model_price_table: list[dict[str, Any]] = []
    reranker_model: str = "BAAI/bge-reranker-base"
    rag_retrieval_top_k: int = 10
    rag_retrieval_min_score: float = 0.1
    rag_rerank_top_k: int = 3
    rag_rerank_min_score: float = 0.5
    knowledge_evidence_transport: Literal["local", "mcp_stdio"] = "local"

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

        object_storage_values = (
            self.input_artifact_object_storage_endpoint_url,
            self.input_artifact_object_storage_bucket,
            (
                self.input_artifact_object_storage_access_key_id.get_secret_value()
                if self.input_artifact_object_storage_access_key_id is not None
                else None
            ),
            (
                self.input_artifact_object_storage_secret_access_key.get_secret_value()
                if self.input_artifact_object_storage_secret_access_key is not None
                else None
            ),
        )
        if any(value is not None for value in object_storage_values) and not all(
            isinstance(value, str) and value.strip() for value in object_storage_values
        ):
            raise ValueError(
                "input artifact object storage settings must be configured together"
            )
        if self.analysis_task_capacity_admission_enabled and not all(
            (
                self.analysis_task_capacity_signal_url,
                self.analysis_task_capacity_signal_token is not None
                and self.analysis_task_capacity_signal_token.get_secret_value(),
            )
        ):
            raise ValueError(
                "capacity admission requires a signal URL and shared token"
            )
        if (
            self.app_env == "production"
            and self.analysis_task_capacity_admission_enabled
            and self.analysis_task_capacity_signal_token is not None
            and self.analysis_task_capacity_signal_token.get_secret_value()
            == DEVELOPMENT_CAPACITY_SIGNAL_TOKEN
        ):
            raise ValueError(
                "ANALYSIS_TASK_CAPACITY_SIGNAL_TOKEN must be configured in production"
            )
        if (
            self.analysis_task_model_max_calls_per_node
            > self.analysis_task_model_max_calls
        ):
            raise ValueError(
                "analysis task model calls per node must not exceed total calls"
            )
        if self.analysis_task_model_max_repairs > self.analysis_task_model_max_calls:
            raise ValueError("analysis task model repairs must not exceed total calls")
        if self.analysis_task_model_max_total_tokens < self.llm_max_output_tokens:
            raise ValueError(
                "analysis task total model tokens must cover one model output"
            )
        return self

    @field_validator("input_artifact_object_storage_public_endpoint_url", mode="before")
    @classmethod
    def normalize_optional_object_storage_public_endpoint(
        cls, value: str | None
    ) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

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
        "input_artifact_document_max_size_mb",
        "input_artifact_upload_lease_seconds",
        "input_artifact_direct_upload_ttl_seconds",
        "input_artifact_table_max_size_mb",
        "input_artifact_image_max_size_mb",
        "input_artifact_clamd_port",
        "input_artifact_clamd_timeout_seconds",
        "input_artifact_ocr_timeout_seconds",
        "input_artifact_image_max_pixels",
        "input_artifact_pdf_render_timeout_seconds",
        "input_artifact_pdf_render_max_side_pixels",
        "input_artifact_pdf_max_ocr_pages",
        "input_artifact_object_storage_health_timeout_seconds",
        "rag_retrieval_top_k",
        "rag_rerank_top_k",
        "analysis_task_company_inflight_limit",
        "analysis_task_global_inflight_limit",
        "analysis_task_admission_retry_after_seconds",
        "analysis_task_capacity_low_watermark_bytes",
        "analysis_task_capacity_signal_max_age_seconds",
        "analysis_task_capacity_signal_timeout_seconds",
        "database_pool_size",
        "database_pool_timeout_seconds",
        "llm_timeout_seconds",
        "analysis_task_model_max_calls",
        "analysis_task_model_max_calls_per_node",
        "analysis_task_model_max_total_tokens",
    )
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Value must be a positive integer")
        return value

    @field_validator("analysis_task_model_max_repairs")
    @classmethod
    def validate_non_negative_model_repairs(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Value must be a non-negative integer")
        return value

    @field_validator("analysis_task_model_max_cost")
    @classmethod
    def validate_positive_model_cost(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("analysis task model max cost must be finite and positive")
        return value

    @field_validator("llm_timeout_seconds")
    @classmethod
    def validate_llm_timeout_against_execution_lease(cls, value: int) -> int:
        if value > MAX_LLM_TIMEOUT_SECONDS:
            raise ValueError(
                f"LLM timeout must not exceed {MAX_LLM_TIMEOUT_SECONDS} seconds"
            )
        return value

    @field_validator("input_artifact_object_storage_health_timeout_seconds")
    @classmethod
    def validate_object_storage_health_timeout(cls, value: int) -> int:
        if value > 10:
            raise ValueError("Object storage health timeout must not exceed 10 seconds")
        return value

    @field_validator("analysis_task_capacity_signal_timeout_seconds")
    @classmethod
    def validate_capacity_signal_timeout(cls, value: int) -> int:
        if value > MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS:
            raise ValueError(
                "Capacity signal timeout must not exceed "
                f"{MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS} seconds"
            )
        return value

    @field_validator("database_max_overflow")
    @classmethod
    def validate_non_negative_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Value must be a non-negative integer")
        return value

    @field_validator("rag_retrieval_min_score", "rag_rerank_min_score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("Score must be between 0 and 1")
        return value

    @field_validator("input_artifact_ocr_minimum_confidence")
    @classmethod
    def validate_ocr_confidence(cls, value: float) -> float:
        if not 0 <= value <= 100:
            raise ValueError("OCR confidence must be between 0 and 100")
        return value

    @field_validator("input_artifact_ocr_languages")
    @classmethod
    def validate_ocr_languages(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OCR languages must not be blank")
        return value

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
