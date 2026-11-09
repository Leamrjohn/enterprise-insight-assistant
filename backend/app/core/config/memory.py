"""Long-term memory: Planner budget, expiry and purge of deleted items."""

from __future__ import annotations

from pydantic import field_validator

from app.core.config.base import ConfigDomain, require_positive


class MemoryConfig(ConfigDomain):
    memory_planner_max_tokens: int = 1024
    memory_ttl_days: int = 30
    # Soft-deleted memories are purged after this many days.
    memory_soft_delete_retention_days: int = 90

    @field_validator(
        "memory_planner_max_tokens",
        "memory_ttl_days",
        "memory_soft_delete_retention_days",
    )
    @classmethod
    def memory_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)
