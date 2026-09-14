"""Durable human-review requests for reports that must not auto-publish."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.workflow.models import AnalysisTask


class ReviewRequest(Base):
    __tablename__ = "review_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="review_request_status_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    task: Mapped["AnalysisTask"] = relationship(
        "AnalysisTask", back_populates="review_request"
    )
