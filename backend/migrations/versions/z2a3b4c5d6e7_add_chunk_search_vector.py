"""Add a full-text search column to document chunks.

Tokens come from Python (jieba), so existing rows stay NULL until
scripts/ops/backfill_chunk_search_vectors.py fills them; a NULL row is simply not
found by keyword search and is still found by vector search.

Revision ID: z2a3b4c5d6e7
Revises: y1a2b3c4d5e6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision = "z2a3b4c5d6e7"
down_revision = "y1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks", sa.Column("search_vector", TSVECTOR(), nullable=True)
    )
    op.create_index(
        "ix_document_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_search_vector", table_name="document_chunks")
    op.drop_column("document_chunks", "search_vector")
