"""scope document content fingerprints to a company

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from alembic import op


revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_documents_sha256", "documents", type_="unique")
    op.create_unique_constraint(
        "documents_company_sha256", "documents", ["company_id", "sha256"]
    )


def downgrade() -> None:
    op.drop_constraint("documents_company_sha256", "documents", type_="unique")
    op.create_unique_constraint("uq_documents_sha256", "documents", ["sha256"])
