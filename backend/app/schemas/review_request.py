"""HTTP contracts for bounded human review decisions."""

from datetime import datetime

from pydantic import BaseModel, Field


class ReviewDecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ReviewDecisionOut(BaseModel):
    task_id: int
    status: str
    review_status: str
    reviewed_at: datetime | None = None
