"""add tool governance, memory provenance and event durations

Revision ID: m0f1a2b3c4d5
Revises: l9e0f1a2b3c4
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m0f1a2b3c4d5"
down_revision = "l9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_events", sa.Column("duration_ms", sa.Integer()))
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "tool_policy_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                '\'{"allowed_tools": ["rag_search", "sql_query", "template_query"], "require_company_scope": true, "require_frozen_document_scope": true}\'::jsonb'
            ),
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "tool_budget_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text(
                '\'{"max_calls": 12, "max_calls_per_tool": 6}\'::jsonb'
            ),
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "tool_budget_usage",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text('\'{"calls": 0, "calls_by_tool": {}}\'::jsonb'),
        ),
    )
    op.create_table(
        "tool_call_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("execution_attempt_id", sa.Integer()),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
    op.create_index("ix_tool_call_records_task_id", "tool_call_records", ["task_id"])
    op.create_index(
        "ix_tool_call_records_execution_attempt_id",
        "tool_call_records",
        ["execution_attempt_id"],
    )
    op.create_index(
        "ix_tool_call_records_tool_name", "tool_call_records", ["tool_name"]
    )
    op.create_table(
        "memory_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source_task_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column(
            "idempotency_key", sa.String(length=128), nullable=False, unique=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_task_id"], ["analysis_tasks.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_memory_sources_company_id", "memory_sources", ["company_id"])
    op.add_column("analysis_memories", sa.Column("memory_source_id", sa.Integer()))
    op.create_foreign_key(
        "analysis_memories_memory_source_id_fkey",
        "analysis_memories",
        "memory_sources",
        ["memory_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_analysis_memories_memory_source_id",
        "analysis_memories",
        ["memory_source_id"],
    )
    op.execute("""
        INSERT INTO memory_sources (company_id, source_task_id, source_type, idempotency_key)
        SELECT company_id, source_task_id, 'validated_report', 'validated-report:' || source_task_id
        FROM analysis_memories
    """)
    op.execute("""
        UPDATE analysis_memories AS memory
        SET memory_source_id = source.id
        FROM memory_sources AS source
        WHERE source.source_task_id = memory.source_task_id
    """)


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_memories_memory_source_id", table_name="analysis_memories"
    )
    op.drop_constraint(
        "analysis_memories_memory_source_id_fkey",
        "analysis_memories",
        type_="foreignkey",
    )
    op.drop_column("analysis_memories", "memory_source_id")
    op.drop_index("ix_memory_sources_company_id", table_name="memory_sources")
    op.drop_table("memory_sources")
    op.drop_index("ix_tool_call_records_tool_name", table_name="tool_call_records")
    op.drop_index(
        "ix_tool_call_records_execution_attempt_id", table_name="tool_call_records"
    )
    op.drop_index("ix_tool_call_records_task_id", table_name="tool_call_records")
    op.drop_table("tool_call_records")
    op.drop_column("analysis_tasks", "tool_budget_usage")
    op.drop_column("analysis_tasks", "tool_budget_snapshot")
    op.drop_column("analysis_tasks", "tool_policy_snapshot")
    op.drop_column("workflow_events", "duration_ms")
