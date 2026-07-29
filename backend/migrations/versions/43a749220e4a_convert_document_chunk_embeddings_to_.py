"""convert document chunk embeddings to vector

Revision ID: 43a749220e4a
Revises: 88b83d61d1f9
Create Date: 2026-07-18 10:35:01.905468

"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "43a749220e4a"
down_revision = "88b83d61d1f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.alter_column(
        "document_chunks",
        "embedding",
        existing_type=sa.ARRAY(sa.DOUBLE_PRECISION()),
        type_=Vector(384),
        existing_nullable=True,
        postgresql_using="embedding::vector(384)",
    )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is not supported because converting vector embeddings "
        "back to arrays is not lossless."
    )
