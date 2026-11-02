"""Add version and validity metadata to documents.

Every column is nullable: a document without metadata stays retrievable, because
its date header is not a reliable validity date.

Revision ID: y1a2b3c4d5e6
Revises: x1a2b3c4d5e6
"""

import sqlalchemy as sa
from alembic import op

revision = "y1a2b3c4d5e6"
down_revision = "x1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("version_group", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("version_number", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("effective_from", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("effective_to", sa.Date(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("superseded_by_document_id", sa.Integer(), nullable=True),
    )
    op.add_column("documents", sa.Column("document_kind", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("applies_to", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_documents_superseded_by",
        "documents",
        "documents",
        ["superseded_by_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "documents_effective_range",
        "documents",
        "effective_from IS NULL OR effective_to IS NULL "
        "OR effective_from <= effective_to",
    )
    op.create_check_constraint(
        "documents_version_fields_together",
        "documents",
        "(version_group IS NULL) = (version_number IS NULL)",
    )
    op.create_check_constraint(
        "documents_superseded_has_end_date",
        "documents",
        "superseded_by_document_id IS NULL OR effective_to IS NOT NULL",
    )
    op.create_unique_constraint(
        "documents_company_version",
        "documents",
        ["company_id", "version_group", "version_number"],
    )


def downgrade() -> None:
    op.drop_constraint("documents_company_version", "documents", type_="unique")
    op.drop_constraint("documents_superseded_has_end_date", "documents", type_="check")
    op.drop_constraint("documents_version_fields_together", "documents", type_="check")
    op.drop_constraint("documents_effective_range", "documents", type_="check")
    op.drop_constraint("fk_documents_superseded_by", "documents", type_="foreignkey")
    op.drop_column("documents", "applies_to")
    op.drop_column("documents", "document_kind")
    op.drop_column("documents", "superseded_by_document_id")
    op.drop_column("documents", "effective_to")
    op.drop_column("documents", "effective_from")
    op.drop_column("documents", "version_number")
    op.drop_column("documents", "version_group")
