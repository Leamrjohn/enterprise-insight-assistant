"""Provenance and idempotency key for durable planner memory."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.memory.models import AnalysisMemory


class MemorySource(Base):
    __tablename__ = "memory_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_task_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    memories: Mapped[list["AnalysisMemory"]] = relationship(back_populates="source")
