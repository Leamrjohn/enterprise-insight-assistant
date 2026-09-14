"""Durable ownership records for individual Worker executions."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.workflow.models import AnalysisTask
    from app.modules.workflow.checkpoint import WorkflowCheckpoint
    from app.modules.workflow.events_models import WorkflowEvent
    from app.modules.workflow.tool_call import ToolCallRecord


class TaskExecutionAttempt(Base):
    __tablename__ = "task_execution_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','retrying','completed','partial','failed','cancelled','expired','superseded')",
            name="task_execution_attempt_status_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        server_default="running",
        index=True,
    )
    worker_id: Mapped[str | None] = mapped_column(String(128))
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    retry_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    latest_checkpoint_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_checkpoints.id", ondelete="SET NULL"), index=True
    )
    workflow_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="v1", server_default="v1"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped["AnalysisTask"] = relationship(
        "AnalysisTask", back_populates="execution_attempts"
    )
    checkpoints: Mapped[list["WorkflowCheckpoint"]] = relationship(
        "WorkflowCheckpoint",
        back_populates="execution",
        cascade="all, delete-orphan",
        foreign_keys="WorkflowCheckpoint.execution_attempt_id",
    )
    workflow_events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )
    tool_call_records: Mapped[list["ToolCallRecord"]] = relationship(
        back_populates="execution"
    )
