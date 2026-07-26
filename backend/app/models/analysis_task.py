from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from datetime import datetime
from typing import Any, Optional
from sqlalchemy.dialects.postgresql import JSONB


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('queued','running','retrying','completed','partial','failed','cancelled','needs_clarification')",
            name="analysistask_status_values",
        ),
        CheckConstraint(
            "stage IN ('queued','planning','querying_data','retrieving_knowledge','composing_report','saving_result','retrying','completed')",
            name="analysistask_task_stage_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_data_sources.id", ondelete="SET NULL"), nullable=True
    )
    schema_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("schema_snapshots.id", ondelete="SET NULL"), nullable=True
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
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
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
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clarification_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )
    clarification_missing_fields: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    resolved_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 自引用关系：parent → children（追问链）
    parent_task: Mapped[Optional["AnalysisTask"]] = relationship(
        "AnalysisTask", remote_side="AnalysisTask.id", back_populates="child_tasks"
    )
    child_tasks: Mapped[list["AnalysisTask"]] = relationship(
        "AnalysisTask", back_populates="parent_task", cascade="all, delete-orphan"
    )

    @property
    def report(self) -> dict[str, Any] | None:
        """Return the stable, client-facing report without exposing workflow layout."""
        if not isinstance(self.result_data, dict):
            return None
        report = self.result_data.get("report")
        return report if isinstance(report, dict) else None


class AnalysisTaskDocument(Base):
    __tablename__ = "analysis_task_documents"

    task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), primary_key=True
    )
