"""preserve document chunk paragraph boundaries

Revision ID: j7c8d9e0f1a2
Revises: i6b7c8d9e0f1
"""

from alembic import op
import sqlalchemy as sa


revision = "j7c8d9e0f1a2"
down_revision = "i6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks", sa.Column("paragraph_start", sa.Integer(), nullable=True)
    )
    op.add_column(
        "document_chunks", sa.Column("paragraph_end", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "paragraph_end")
    op.drop_column("document_chunks", "paragraph_start")
