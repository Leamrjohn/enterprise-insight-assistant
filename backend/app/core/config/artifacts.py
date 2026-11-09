"""Document uploads and input artifacts.  The upload entry is frozen (AGENTS.md):
these settings moved here unchanged and must not change behavior."""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator

from app.core.config.base import ConfigDomain, require_positive


class ArtifactConfig(ConfigDomain):
    max_upload_size_mb: int = 20
    allowed_document_extensions: list[str] = Field(
        default_factory=lambda: [".txt", ".pdf", ".md", ".markdown"]
    )
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

    @field_validator("input_artifact_object_storage_public_endpoint_url", mode="before")
    @classmethod
    def artifacts_normalize_optional_object_storage_public_endpoint(
        cls, value: str | None
    ) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

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
    )
    @classmethod
    def artifacts_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("input_artifact_object_storage_health_timeout_seconds")
    @classmethod
    def artifacts_validate_object_storage_health_timeout(cls, value: int) -> int:
        if value > 10:
            raise ValueError("Object storage health timeout must not exceed 10 seconds")
        return value

    @field_validator("input_artifact_ocr_minimum_confidence")
    @classmethod
    def artifacts_validate_ocr_confidence(cls, value: float) -> float:
        if not 0 <= value <= 100:
            raise ValueError("OCR confidence must be between 0 and 100")
        return value

    @field_validator("input_artifact_ocr_languages")
    @classmethod
    def artifacts_validate_ocr_languages(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OCR languages must not be blank")
        return value
