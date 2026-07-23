from sqlalchemy import ForeignKey, String, Text, DateTime, func, CheckConstraint
from app.db.base import Base
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Any
from sqlalchemy.dialects.postgresql import JSONB


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('queued','running','retrying','completed','partial','failed','cancelled')",
            name="analysistask_status_values",
        ),
        CheckConstraint(
            "stage IN ('queued','search_evidence','check_sufficiency','build_prompt','call_model','save_result','completed')",
            name="analysistask_task_stage_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    input_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
        index=True,
    )
    stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
    )
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
