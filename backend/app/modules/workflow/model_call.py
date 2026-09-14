"""Privacy-safe audit metadata for one governed model invocation."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.workflow.models import AnalysisTask
    from app.modules.workflow.execution_attempt import TaskExecutionAttempt


class ModelCallRecord(Base):
    __tablename__ = "model_call_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_execution_attempts.id", ondelete="SET NULL"), index=True
    )
    node_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_category: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    task: Mapped["AnalysisTask"] = relationship(
        "AnalysisTask", back_populates="model_call_records"
    )
    execution_attempt: Mapped["TaskExecutionAttempt | None"] = relationship(
        "TaskExecutionAttempt"
    )
