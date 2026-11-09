"""How much conversation history and evidence a model prompt may carry."""

from __future__ import annotations

from pydantic import field_validator

from app.core.config.base import ConfigDomain, require_positive


class ContextConfig(ConfigDomain):
    # conversations/service.py: tokens of earlier turns passed to the Planner.
    context_history_max_tokens: int = 2048
    # runtime/context_budget.py: compress once a prompt reaches this share of
    # its budget, keeping at most these rows and characters per item.
    context_compress_at: float = 0.8
    context_max_rows_when_compressed: int = 20
    context_max_chunk_chars_when_compressed: int = 800

    @field_validator(
        "context_history_max_tokens",
        "context_max_rows_when_compressed",
        "context_max_chunk_chars_when_compressed",
    )
    @classmethod
    def context_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)

    @field_validator("context_compress_at")
    @classmethod
    def context_validate_share(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("Compression threshold must be in (0, 1]")
        return value
