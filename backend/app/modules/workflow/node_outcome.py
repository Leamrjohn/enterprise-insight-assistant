"""Stable machine-readable result contract for every workflow node."""

from typing import Any, Literal

from pydantic import BaseModel, Field


NodeStatus = Literal[
    "succeeded",
    "no_matching_records",
    "insufficient_evidence",
    "retryable_error",
    "repairable_error",
    "denied",
    "cancelled",
]
RetryHint = Literal["retry", "repair", "stop"]


class NodeOutcome(BaseModel):
    status: NodeStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    retry_hint: RetryHint = "stop"
    checkpoint_patch: dict[str, Any] = Field(default_factory=dict)
