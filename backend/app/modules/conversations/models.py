"""Conversation and display-message persistence models."""

from __future__ import annotations

from datetime import datetime

from app.db.base import Base
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    data_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_data_sources.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (ConversationMessage.created_at, ConversationMessage.id),
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="role_values",
        ),
        CheckConstraint(
            "status IN ("
            "'queued', 'running', 'awaiting_review', 'completed', 'partial', "
            "'failed', 'cancelled', 'needs_clarification'"
            ")",
            name="status_values",
        ),
        CheckConstraint(
            "analysis_task_id IS NULL OR role = 'assistant'",
            name="task_only_for_assistant",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    analysis_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
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

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ConversationState(Base):
    """Standing constraints and current subject of one conversation (C6).

    Written only by code after a task is published; ``version`` is the
    optimistic lock, so a stale writer updates nothing.
    """

    __tablename__ = "conversation_states"
    __table_args__ = (CheckConstraint("version >= 1", name="version_positive"),)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    last_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ConversationSummary(Base):
    """What the messages that left the context window said (C9).

    Kept apart from ``ConversationState``: the summary is written by its own
    job, so each has its own ``version`` lock and neither write loses to the
    other.  Every item cites the messages it came from.
    """

    __tablename__ = "conversation_summaries"
    __table_args__ = (CheckConstraint("version >= 1", name="version_positive"),)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    last_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
