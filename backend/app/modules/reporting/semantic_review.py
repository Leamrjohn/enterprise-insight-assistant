"""Structured model-review contracts for plans, SQL candidates, and evidence."""

from typing import Literal

from pydantic import BaseModel, Field


class SQLSemanticReview(BaseModel):
    decision: Literal["execute", "repair", "insufficient_schema"]
    reason: str = Field(min_length=1, max_length=500)
    missing_requirements: list[str] = Field(default_factory=list, max_length=12)


class DocumentQualificationReview(BaseModel):
    """One exact source boundary proposed by semantic review."""

    statement: str = Field(min_length=1, max_length=500)
    citation_chunk_ids: list[int] = Field(min_length=1, max_length=8)


class EvidenceSemanticReview(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str = Field(min_length=1, max_length=500)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    supported_document_chunk_ids: list[int] = Field(default_factory=list, max_length=8)
    document_qualifications: list[DocumentQualificationReview] = Field(
        default_factory=list, max_length=8
    )
