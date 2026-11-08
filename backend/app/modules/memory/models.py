"""Planner-only durable memory derived from already validated reports."""

from datetime import date, datetime
from typing import Any

from app.db.base import Base
from app.modules.memory.sources import MemorySource
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class AnalysisMemory(Base):
    __tablename__ = "analysis_memories"

    __table_args__ = (
        CheckConstraint(
            "layer IN ('session', 'fact', 'preference', 'experience')",
            name="analysis_memories_layer",
        ),
        CheckConstraint(
            "status IN ('active', 'flagged', 'superseded', 'revoked', 'deleted')",
            name="analysis_memories_status",
        ),
        Index("ix_analysis_memories_selection", "company_id", "user_id", "status"),
        Index("ix_analysis_memories_subject", "company_id", "user_id", "subject_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    memory_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("memory_sources.id", ondelete="CASCADE"), index=True
    )
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    layer: Mapped[str] = mapped_column(
        String(16), nullable=False, default="fact", server_default="fact"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5"
    )
    importance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5"
    )
    # What the memory is about; a newer memory with the same key replaces it.
    subject_key: Mapped[str | None] = mapped_column(String(64))
    # When the fact stops being true in the business, unlike expires_at, which is
    # how long we keep it.
    business_valid_until: Mapped[date | None] = mapped_column(Date)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    use_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_memories.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped["MemorySource | None"] = relationship(back_populates="memories")


class MemoryAuditEvent(Base):
    __tablename__ = "memory_audit_events"

    __table_args__ = (
        CheckConstraint(
            "actor_kind IN ('system', 'model', 'user')",
            name="memory_audit_events_actor_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_memories.id", ondelete="SET NULL"), index=True
    )
    # Kept as a plain number so the trail still names a physically deleted memory.
    original_memory_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
