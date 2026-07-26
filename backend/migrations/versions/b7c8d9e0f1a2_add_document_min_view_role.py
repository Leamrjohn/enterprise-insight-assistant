"""add document minimum visibility role

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
"""

from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("documents", "user_id", new_column_name="uploaded_by_user_id")
    op.add_column("documents", sa.Column("min_view_role", sa.String(length=20), nullable=False, server_default="any"))
    op.create_check_constraint("documents_min_view_role_values", "documents", "min_view_role IN ('any', 'admin', 'owner')")


def downgrade() -> None:
    raise NotImplementedError("document visibility migration is irreversible")
