from app.db.base import Base
from sqlalchemy import (
    ForeignKey,
    String,
    DateTime,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (
        UniqueConstraint("name", "user_id", name="uq_label_name_user_id_name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#3B82F6", server_default="#3B82F6"
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
