from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from app.modules.workflow.execution_attempt import TaskExecutionAttempt
    from app.modules.workflow.model_call import ModelCallRecord
    from app.modules.reviews.models import ReviewRequest
    from app.modules.workflow.events_models import WorkflowEvent
    from app.modules.workflow.tool_call import ToolCallRecord


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('queued','running','retrying','awaiting_review','completed','partial','failed','cancelled','needs_clarification')",
            name="analysistask_status_values",
        ),
        CheckConstraint(
            "stage IN ('queued','planning','querying_data','retrieving_knowledge','composing_report','saving_result','awaiting_review','retrying','completed')",
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
    request_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    active_execution_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    model_policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "primary_model": "configured-default",
            "fallback_models": [],
            "require_json": False,
            "allow_tool_calling": False,
            "timeout_seconds": 30,
            "max_attempts": 3,
        },
    )
    model_budget_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "max_calls": 12,
            "max_calls_per_node": 4,
            "max_repairs": 2,
            "max_total_tokens": 12000,
            "max_cost": "1.00",
        },
    )
    model_budget_usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "calls": 0,
            "tokens": 0,
            "cost": "0.00",
            "repairs": 0,
            "calls_by_node": {},
        },
    )
    tool_policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "allowed_tools": ["rag_search", "sql_query", "template_query"],
            "require_company_scope": True,
            "require_frozen_document_scope": True,
        },
    )
    tool_budget_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {"max_calls": 12, "max_calls_per_tool": 6},
    )
    tool_budget_usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=lambda: {"calls": 0, "calls_by_tool": {}}
    )
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
    execution_attempts: Mapped[list["TaskExecutionAttempt"]] = relationship(
        "TaskExecutionAttempt", back_populates="task", cascade="all, delete-orphan"
    )
    model_call_records: Mapped[list["ModelCallRecord"]] = relationship(
        "ModelCallRecord", back_populates="task", cascade="all, delete-orphan"
    )
    review_request: Mapped["ReviewRequest | None"] = relationship(
        "ReviewRequest",
        back_populates="task",
        cascade="all, delete-orphan",
        uselist=False,
    )
    workflow_events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    tool_call_records: Mapped[list["ToolCallRecord"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
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


# Relationship targets must be registered even in processes that only import
# AnalysisTask (for example, the isolated workflow test process).
from app.modules.workflow.execution_attempt import TaskExecutionAttempt  # noqa: E402, F401
from app.modules.workflow.checkpoint import WorkflowCheckpoint  # noqa: E402, F401
from app.modules.workflow.model_call import ModelCallRecord  # noqa: E402, F401
from app.modules.reviews.models import ReviewRequest  # noqa: E402, F401
from app.modules.workflow.events_models import WorkflowEvent  # noqa: E402, F401
from app.modules.workflow.tool_call import ToolCallRecord  # noqa: E402, F401
from app.modules.memory.sources import MemorySource  # noqa: E402, F401
from app.modules.memory.models import AnalysisMemory  # noqa: E402, F401
