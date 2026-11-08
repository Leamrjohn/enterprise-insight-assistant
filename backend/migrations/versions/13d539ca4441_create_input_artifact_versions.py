"""create input artifact versions

Revision ID: 13d539ca4441
Revises: dac443e0de0e
Create Date: 2026-09-10 09:39:17.532175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13d539ca4441'
down_revision: Union[str, Sequence[str], None] = 'dac443e0de0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "input_artifact_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("raw_object_key", sa.String(length=512), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("declared_mime_type", sa.String(length=255), nullable=True),
        sa.Column("detected_mime_type", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="received",
            nullable=False,
        ),
        sa.Column("status_reason_code", sa.String(length=64), nullable=True),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('received', 'scanning', 'parsing', 'ready', 'rejected', 'failed')",
            name="status_values",
        ),
        sa.CheckConstraint(
            "(status IN ('rejected', 'failed') AND status_reason_code IS NOT NULL) "
            "OR (status NOT IN ('rejected', 'failed') AND status_reason_code IS NULL)",
            name="status_reason_matches_status",
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="version_number_positive",
        ),
        sa.UniqueConstraint(
            "artifact_id",
            "version_number",
            name="uq_input_artifact_versions_artifact_id_with_version_number",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["input_artifacts.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_input_artifact_versions_artifact_id",
        "input_artifact_versions",
        ["artifact_id"],
    )
    op.create_index(
        "ix_input_artifact_versions_status",
        "input_artifact_versions",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_input_artifact_versions_status",
        table_name="input_artifact_versions",
    )
    op.drop_index(
        "ix_input_artifact_versions_artifact_id",
        table_name="input_artifact_versions",
    )
    op.drop_table("input_artifact_versions")
