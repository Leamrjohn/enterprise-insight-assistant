"""Append-only audit records for workflow and tool execution."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_task import AnalysisTask
    from app.models.task_execution_attempt import TaskExecutionAttempt


class WorkflowEvent(Base):
    """A durable, redacted event; it is not used to reconstruct workflow state."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint(
            "execution_attempt_id", "sequence", name="uq_workflow_event_sequence"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("task_execution_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[int | None] = mapped_column(index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    node_name: Mapped[str | None] = mapped_column(String(64))
    tool_name: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(128))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    task: Mapped["AnalysisTask"] = relationship(back_populates="workflow_events")
    execution: Mapped["TaskExecutionAttempt"] = relationship(
        back_populates="workflow_events"
    )
