"""harden input artifact versions

Revision ID: 7e9b1c3d5f7a
Revises: 6c8e0a2d4f6b
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7e9b1c3d5f7a"
down_revision: Union[str, Sequence[str], None] = "6c8e0a2d4f6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "input_artifact_versions",
        sa.Column("declared_extension", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "byte_size_non_negative",
        "input_artifact_versions",
        "byte_size >= 0",
    )
    op.create_check_constraint(
        "sha256_lower_hex",
        "input_artifact_versions",
        "sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_unique_constraint(
        "uq_input_artifact_versions_raw_object_key",
        "input_artifact_versions",
        ["raw_object_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_input_artifact_versions_raw_object_key",
        "input_artifact_versions",
        type_="unique",
    )
    op.drop_constraint(
        "sha256_lower_hex",
        "input_artifact_versions",
        type_="check",
    )
    op.drop_constraint(
        "byte_size_non_negative",
        "input_artifact_versions",
        type_="check",
    )
    op.drop_column("input_artifact_versions", "declared_extension")
