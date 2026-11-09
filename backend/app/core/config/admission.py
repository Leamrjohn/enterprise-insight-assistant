"""How many analysis tasks may run, and the disk-capacity admission signal."""

from __future__ import annotations

from pydantic import SecretStr, field_validator

from app.core.config.base import ConfigDomain, require_positive

MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS = 5
DEVELOPMENT_CAPACITY_SIGNAL_TOKEN = "local-capacity-signal-development-only"


class AdmissionConfig(ConfigDomain):
    analysis_task_company_inflight_limit: int = 5
    analysis_task_global_inflight_limit: int = 20
    analysis_task_admission_retry_after_seconds: int = 30
    analysis_task_capacity_admission_enabled: bool = False
    analysis_task_capacity_signal_url: str | None = None
    analysis_task_capacity_signal_token: SecretStr | None = None
    analysis_task_capacity_low_watermark_bytes: int = 536_870_912
    analysis_task_capacity_signal_max_age_seconds: int = 5
    analysis_task_capacity_signal_timeout_seconds: int = 1

    @field_validator(
        "analysis_task_company_inflight_limit",
        "analysis_task_global_inflight_limit",
        "analysis_task_admission_retry_after_seconds",
        "analysis_task_capacity_low_watermark_bytes",
        "analysis_task_capacity_signal_max_age_seconds",
        "analysis_task_capacity_signal_timeout_seconds",
    )
    @classmethod
    def admission_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("analysis_task_capacity_signal_timeout_seconds")
    @classmethod
    def admission_validate_capacity_signal_timeout(cls, value: int) -> int:
        if value > MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS:
            raise ValueError(
                "Capacity signal timeout must not exceed "
                f"{MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS} seconds"
            )
        return value
