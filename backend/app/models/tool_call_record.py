"""Privacy-safe audit metadata for one governed Tool invocation."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis_task import AnalysisTask
    from app.models.task_execution_attempt import TaskExecutionAttempt


class ToolCallRecord(Base):
    __tablename__ = "tool_call_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_execution_attempts.id", ondelete="SET NULL"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    task: Mapped["AnalysisTask"] = relationship(back_populates="tool_call_records")
    execution: Mapped["TaskExecutionAttempt | None"] = relationship(
        back_populates="tool_call_records"
    )
