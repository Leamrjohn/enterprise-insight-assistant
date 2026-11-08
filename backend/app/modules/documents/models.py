from datetime import date, datetime

from app.db.base import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class Documents(Base):
    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','completed', 'failed', 'processing')",
            name="status_values",
        ),
        CheckConstraint(
            "effective_from IS NULL OR effective_to IS NULL "
            "OR effective_from <= effective_to",
            name="documents_effective_range",
        ),
        CheckConstraint(
            "(version_group IS NULL) = (version_number IS NULL)",
            name="documents_version_fields_together",
        ),
        CheckConstraint(
            "superseded_by_document_id IS NULL OR effective_to IS NOT NULL",
            name="documents_superseded_has_end_date",
        ),
        UniqueConstraint("company_id", "sha256", name="documents_company_sha256"),
        UniqueConstraint(
            "company_id",
            "version_group",
            "version_number",
            name="documents_company_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="completed",
        server_default="completed",
        index=True,
    )
    min_view_role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="any", server_default="any"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set only through versioning.register_document_version; NULL means unknown,
    # and an unknown document is not filtered out of retrieval.
    version_group: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    superseded_by_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    document_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
