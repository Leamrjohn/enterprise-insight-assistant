"""Minimal, payload-free audit record for denied analysis submissions."""

from __future__ import annotations

from datetime import datetime
from logging import getLogger

from app.db.base import Base
from app.db.session import SessionLocal, set_tenant_scope
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

logger = getLogger(__name__)


class AnalysisRequestRejection(Base):
    __tablename__ = "analysis_request_rejections"
    __table_args__ = (
        CheckConstraint("status_code BETWEEN 400 AND 499", name="client_error_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def record_analysis_request_rejection(
    *, company_id: int, request_id: str, operation: str, status_code: int
) -> None:
    """Persist one correlation record without changing an already-denied response."""
    db = SessionLocal()
    try:
        set_tenant_scope(db, company_id)
        db.add(
            AnalysisRequestRejection(
                company_id=company_id,
                request_id=request_id,
                operation=operation,
                status_code=status_code,
            )
        )
        db.commit()
    except IntegrityError:
        # A client can replay its request ID. The original denial remains the
        # authoritative audit event and the HTTP response must stay unchanged.
        db.rollback()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to persist analysis request rejection audit")
    finally:
        db.close()
