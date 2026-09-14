"""Recoverable, ordered workflow snapshots for one execution attempt."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.workflow.execution_attempt import TaskExecutionAttempt


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "execution_attempt_id", "sequence", name="uq_workflow_checkpoint_sequence"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("task_execution_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_node: Mapped[str | None] = mapped_column(String(64))
    next_node: Mapped[str | None] = mapped_column(String(64))
    state_patch: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    error_code: Mapped[str | None] = mapped_column(String(128))
    recovery_instruction: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    execution: Mapped["TaskExecutionAttempt"] = relationship(
        "TaskExecutionAttempt",
        back_populates="checkpoints",
        foreign_keys=[execution_attempt_id],
    )
