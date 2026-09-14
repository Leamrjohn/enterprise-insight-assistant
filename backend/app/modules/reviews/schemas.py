"""HTTP contracts for bounded human review decisions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.reporting.schemas import FinalAnalysisReport


ReviewStatus = Literal["pending", "approved", "rejected"]
TaskStatus = Literal[
    "queued",
    "running",
    "retrying",
    "awaiting_review",
    "completed",
    "partial",
    "failed",
    "cancelled",
    "needs_clarification",
]


class ReviewDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ReviewDecisionOut(BaseModel):
    task_id: int
    status: TaskStatus
    review_status: ReviewStatus
    reviewed_at: datetime | None = None


class ReviewRequestOut(BaseModel):
    """Safe queue item for a company administrator's review workspace."""

    id: int
    task_id: int
    task_question: str
    status: ReviewStatus
    reason_code: str
    report_draft: FinalAnalysisReport | None
    draft_error: Literal["missing", "invalid"] | None = None
    created_at: datetime
