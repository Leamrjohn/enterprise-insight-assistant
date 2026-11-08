"""add embedding column to document_chunks

Revision ID: add_embedding_column
Revises: 12385efc580f
Create Date: 2026-07-11 21:11:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_embedding_column"
down_revision: Union[str, Sequence[str], None] = "12385efc580f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding")
