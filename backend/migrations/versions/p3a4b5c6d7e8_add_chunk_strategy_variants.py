"""store versioned document chunk variants side by side

Revision ID: p3a4b5c6d7e8
Revises: o2b3c4d5e6f7
"""

import sqlalchemy as sa
from alembic import op

revision = "p3a4b5c6d7e8"
down_revision = "o2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "chunk_strategy",
            sa.Text(),
            nullable=False,
            server_default="paragraph_v1",
        ),
    )
    op.drop_constraint(
        "uq_document_chunks_document_id_chunk_index",
        "document_chunks",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_strategy_index",
        "document_chunks",
        ["document_id", "chunk_strategy", "chunk_index"],
    )
    op.drop_index("ix_document_chunks_company_document", table_name="document_chunks")
    op.create_index(
        "ix_document_chunks_company_document_strategy",
        "document_chunks",
        ["company_id", "document_id", "chunk_strategy"],
    )


def downgrade() -> None:
    # The prior schema permits only one chunk_index per document.  A rollback
    # deliberately discards the candidate representation and preserves the
    # migrated/current paragraph baseline before restoring that invariant.
    op.execute(
        "DELETE FROM document_chunks WHERE chunk_strategy <> 'paragraph_v1'"
    )
    op.drop_index(
        "ix_document_chunks_company_document_strategy", table_name="document_chunks"
    )
    op.create_index(
        "ix_document_chunks_company_document",
        "document_chunks",
        ["company_id", "document_id"],
    )
    op.drop_constraint(
        "uq_document_chunks_document_strategy_index",
        "document_chunks",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_id_chunk_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    op.drop_column("document_chunks", "chunk_strategy")
