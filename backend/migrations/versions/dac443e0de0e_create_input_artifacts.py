"""create input artifacts

Revision ID: dac443e0de0e
Revises: m0f1a2b3c4d5
Create Date: 2026-09-10 09:22:27.236884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dac443e0de0e'
down_revision: Union[str, Sequence[str], None] = 'm0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "input_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('attachment', 'knowledge_document', 'dataset')",
            name="input_artifact_kind_values",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_input_artifacts_company_id",
        "input_artifacts",
        ["company_id"],
    )
    op.create_index(
        "ix_input_artifacts_uploaded_by_user_id",
        "input_artifacts",
        ["uploaded_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_input_artifacts_uploaded_by_user_id",
        table_name="input_artifacts",
    )
    op.drop_index(
        "ix_input_artifacts_company_id",
        table_name="input_artifacts",
    )
    op.drop_table("input_artifacts")
