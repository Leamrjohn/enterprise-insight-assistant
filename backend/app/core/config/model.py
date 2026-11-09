"""Model provider, per-task model budget and node retry counts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator

from app.core.config.base import ConfigDomain, require_non_negative, require_positive

EXECUTION_LEASE_SECONDS = 120
# A provider call must leave at least half the execution lease for failure and recovery.
MAX_LLM_TIMEOUT_SECONDS = EXECUTION_LEASE_SECONDS // 2


class ModelConfig(ConfigDomain):
    llm_provider: Literal["local", "openai", "deepseek"] = "deepseek"
    llm_model: str = "deepseek-chat"
    openai_api_key: SecretStr | None = None
    llm_timeout_seconds: int = 30
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 1024
    analysis_task_model_max_calls: int = 8
    analysis_task_model_max_calls_per_node: int = 4
    analysis_task_model_max_repairs: int = 2
    analysis_task_model_max_total_tokens: int = 16000
    analysis_task_model_max_cost: Decimal = Decimal("0.15")
    # Model attempts per node before the task fails (planning.py, data_agent.py).
    planner_max_attempts: int = 2
    data_max_attempts: int = 2
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    model_price_table_version: str = "unconfigured"
    model_price_table: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator(
        "llm_timeout_seconds",
        "analysis_task_model_max_calls",
        "analysis_task_model_max_calls_per_node",
        "analysis_task_model_max_total_tokens",
        "planner_max_attempts",
        "data_max_attempts",
    )
    @classmethod
    def model_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("analysis_task_model_max_repairs")
    @classmethod
    def model_validate_non_negative_model_repairs(cls, value: int) -> int:
        return require_non_negative(value)

    @field_validator("analysis_task_model_max_cost")
    @classmethod
    def model_validate_positive_model_cost(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("analysis task model max cost must be finite and positive")
        return value

    @field_validator("llm_timeout_seconds")
    @classmethod
    def model_validate_llm_timeout_against_execution_lease(cls, value: int) -> int:
        if value > MAX_LLM_TIMEOUT_SECONDS:
            raise ValueError(
                f"LLM timeout must not exceed {MAX_LLM_TIMEOUT_SECONDS} seconds"
            )
        return value
