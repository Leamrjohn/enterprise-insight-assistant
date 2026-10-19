"""Privacy-safe audit metadata for one governed model invocation."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.db.base import Base
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
    from app.modules.workflow.models import AnalysisTask


class ModelCallRecord(Base):
    __tablename__ = "model_call_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_call_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, default=lambda: str(uuid4())
    )
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
    prompt_template_id: Mapped[str | None] = mapped_column(String(80))
    prompt_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    model_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    price_table_version: Mapped[str | None] = mapped_column(String(64))
    pricing_key: Mapped[str | None] = mapped_column(String(128))
    charge_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="provider_model"
    )
    billing_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", index=True
    )
    reserved_prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    reserved_completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    reserved_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resource_usage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_category: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped["AnalysisTask"] = relationship(
        "AnalysisTask", back_populates="model_call_records"
    )
    execution_attempt: Mapped["TaskExecutionAttempt | None"] = relationship(
        "TaskExecutionAttempt"
    )
