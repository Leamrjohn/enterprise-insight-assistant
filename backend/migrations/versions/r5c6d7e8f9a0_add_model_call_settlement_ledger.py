"""add durable model-call reservation and settlement state

Revision ID: r5c6d7e8f9a0
Revises: q4b5c6d7e8f9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "r5c6d7e8f9a0"
down_revision = "q4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_call_records", sa.Column("model_call_id", sa.String(36), nullable=True)
    )
    op.execute(
        "UPDATE model_call_records "
        "SET model_call_id = 'legacy-' || id::text "
        "WHERE model_call_id IS NULL"
    )
    op.alter_column("model_call_records", "model_call_id", nullable=False)
    op.create_unique_constraint(
        "uq_model_call_records_model_call_id", "model_call_records", ["model_call_id"]
    )
    op.add_column(
        "model_call_records", sa.Column("price_table_version", sa.String(64))
    )
    op.add_column("model_call_records", sa.Column("pricing_key", sa.String(128)))
    op.add_column(
        "model_call_records",
        sa.Column(
            "charge_kind",
            sa.String(32),
            nullable=False,
            server_default="provider_model",
        ),
    )
    op.add_column(
        "model_call_records",
        sa.Column(
            "billing_status", sa.String(16), nullable=False, server_default="unknown"
        ),
    )
    op.create_index(
        "ix_model_call_records_billing_status", "model_call_records", ["billing_status"]
    )
    op.add_column(
        "model_call_records",
        sa.Column(
            "reserved_prompt_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "model_call_records",
        sa.Column(
            "reserved_completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("model_call_records", sa.Column("reserved_cost", sa.Numeric(12, 6)))
    op.alter_column(
        "model_call_records",
        "cost",
        existing_type=sa.Numeric(12, 6),
        nullable=True,
        server_default=None,
    )
    op.add_column(
        "model_call_records",
        sa.Column(
            "resource_usage",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "model_call_records", sa.Column("settled_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("model_call_records", "settled_at")
    op.drop_column("model_call_records", "resource_usage")
    op.alter_column(
        "model_call_records",
        "cost",
        existing_type=sa.Numeric(12, 6),
        nullable=False,
        server_default="0",
    )
    op.drop_column("model_call_records", "reserved_cost")
    op.drop_column("model_call_records", "reserved_completion_tokens")
    op.drop_column("model_call_records", "reserved_prompt_tokens")
    op.drop_index(
        "ix_model_call_records_billing_status", table_name="model_call_records"
    )
    op.drop_column("model_call_records", "billing_status")
    op.drop_column("model_call_records", "charge_kind")
    op.drop_column("model_call_records", "pricing_key")
    op.drop_column("model_call_records", "price_table_version")
    op.drop_constraint(
        "uq_model_call_records_model_call_id", "model_call_records", type_="unique"
    )
    op.drop_column("model_call_records", "model_call_id")
