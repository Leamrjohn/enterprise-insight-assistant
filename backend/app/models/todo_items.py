from app.db.base import Base
from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    DateTime,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime


class TodoItem(Base):
    __tablename__ = "todo_items"

    __table_args__ = (
        CheckConstraint(
            "status IN ('todo','in_progress', 'done')",
            name="todo_item_status_values",
        ),
        CheckConstraint(
            "priority IN ('low','medium','high')",
            name="todo_item_priority_values",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="todo", server_default="todo", nullable=False, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), default="medium", server_default="medium", nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
