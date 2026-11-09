"""Model-chosen tools inside Data and Knowledge, and the tool loop limits."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.core.config.base import ConfigDomain, require_non_negative, require_positive


class ToolConfig(ConfigDomain):
    # Model-chosen tools inside Data and Knowledge. "allowlist" is the gradual rollout.
    model_tool_mode: Literal["off", "allowlist", "all"] = "off"
    model_tool_company_ids: list[int] = Field(default_factory=list)
    knowledge_evidence_transport: Literal["local", "mcp_stdio"] = "local"
    # runtime/tool_loop.py LoopLimits; Knowledge uses its own rounds and calls.
    tool_loop_max_rounds: int = 6
    tool_loop_max_tool_calls: int = 8
    tool_loop_max_repairs: int = 2
    tool_loop_max_seconds: float = 90.0
    tool_loop_model_retries: int = 1
    tool_loop_backoff_seconds: float = 1.0
    knowledge_tool_loop_max_rounds: int = 4
    knowledge_tool_loop_max_tool_calls: int = 5

    @field_validator(
        "tool_loop_max_rounds",
        "tool_loop_max_tool_calls",
        "knowledge_tool_loop_max_rounds",
        "knowledge_tool_loop_max_tool_calls",
    )
    @classmethod
    def tool_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("tool_loop_max_repairs", "tool_loop_model_retries")
    @classmethod
    def tool_validate_non_negative_int(cls, value: int) -> int:
        return require_non_negative(value)

    @field_validator("tool_loop_max_seconds", "tool_loop_backoff_seconds")
    @classmethod
    def tool_validate_seconds(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Seconds must not be negative")
        return value
