"""add task model governance snapshots and privacy-safe call records

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "model_policy_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                '\'{"primary_model": "configured-default", "fallback_models": [], '
                '"require_json": false, "allow_tool_calling": false, '
                '"timeout_seconds": 30, "max_attempts": 3}\'::jsonb'
            ),
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "model_budget_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                '\'{"max_calls": 12, "max_calls_per_node": 4, "max_repairs": 2, '
                '"max_total_tokens": 12000, "max_cost": "1.00"}\'::jsonb'
            ),
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "model_budget_usage",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                '\'{"calls": 0, "tokens": 0, "cost": "0.00", '
                '"repairs": 0, "calls_by_node": {}}\'::jsonb'
            ),
        ),
    )
    op.create_table(
        "model_call_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("execution_attempt_id", sa.Integer()),
        sa.Column("node_name", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "completion_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_category", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_attempt_id"],
            ["task_execution_attempts.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_model_call_records_task_id", "model_call_records", ["task_id"])
    op.create_index(
        "ix_model_call_records_execution_attempt_id",
        "model_call_records",
        ["execution_attempt_id"],
    )
    op.create_index(
        "ix_model_call_records_node_name", "model_call_records", ["node_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_model_call_records_node_name", table_name="model_call_records")
    op.drop_index(
        "ix_model_call_records_execution_attempt_id", table_name="model_call_records"
    )
    op.drop_index("ix_model_call_records_task_id", table_name="model_call_records")
    op.drop_table("model_call_records")
    op.drop_column("analysis_tasks", "model_budget_usage")
    op.drop_column("analysis_tasks", "model_budget_snapshot")
    op.drop_column("analysis_tasks", "model_policy_snapshot")
