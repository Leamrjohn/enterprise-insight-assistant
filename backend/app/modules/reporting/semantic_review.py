"""Structured model-review contracts for plans, SQL candidates, and evidence."""

from typing import Literal

from pydantic import BaseModel, Field


class SQLSemanticReview(BaseModel):
    decision: Literal["execute", "repair", "insufficient_schema"]
    reason: str = Field(min_length=1, max_length=500)
    missing_requirements: list[str] = Field(default_factory=list, max_length=12)


class EvidenceSemanticReview(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str = Field(min_length=1, max_length=500)
    limitations: list[str] = Field(default_factory=list, max_length=8)
