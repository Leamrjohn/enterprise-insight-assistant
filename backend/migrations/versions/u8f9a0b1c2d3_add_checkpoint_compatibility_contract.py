"""add workflow checkpoint compatibility contract

Revision ID: u8f9a0b1c2d3
Revises: t7e8f9a0b1c2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "t7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_checkpoints",
        sa.Column(
            "schema_version",
            sa.String(64),
            nullable=False,
            server_default="legacy-unverified",
        ),
    )
    op.add_column(
        "workflow_checkpoints",
        sa.Column(
            "task_input_fingerprint",
            sa.String(64),
            nullable=False,
            server_default="legacy-unverified",
        ),
    )


def downgrade() -> None:
    op.drop_column("workflow_checkpoints", "task_input_fingerprint")
    op.drop_column("workflow_checkpoints", "schema_version")
