"""add execution provenance

Revision ID: o2b3c4d5e6f7
Revises: n1a2b3c4d5e6
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "o2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "n1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_call_records", sa.Column("prompt_template_id", sa.String(80)))
    op.add_column("model_call_records", sa.Column("prompt_hash", sa.String(64)))
    op.add_column(
        "model_call_records",
        sa.Column(
            "model_parameters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_model_call_records_prompt_hash", "model_call_records", ["prompt_hash"])
    op.add_column(
        "tool_call_records",
        sa.Column(
            "tool_contract_version",
            sa.String(64),
            nullable=False,
            server_default="tool-contract/v1",
        ),
    )


def downgrade() -> None:
    op.drop_column("tool_call_records", "tool_contract_version")
    op.drop_index("ix_model_call_records_prompt_hash", table_name="model_call_records")
    op.drop_column("model_call_records", "model_parameters")
    op.drop_column("model_call_records", "prompt_hash")
    op.drop_column("model_call_records", "prompt_template_id")
