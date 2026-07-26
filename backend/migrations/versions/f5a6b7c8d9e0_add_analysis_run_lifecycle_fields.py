"""add analysis run lifecycle fields (started_at, completed_at, clarification, parent_task)

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增时间戳字段
    op.add_column(
        "analysis_tasks",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. 新增追问相关字段
    op.add_column(
        "analysis_tasks",
        sa.Column("clarification_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "clarification_missing_fields",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("resolved_question", sa.Text(), nullable=True),
    )

    # 3. 新增追问链父任务字段
    op.add_column(
        "analysis_tasks",
        sa.Column("parent_task_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_analysis_tasks_parent_task",
        "analysis_tasks",
        "analysis_tasks",
        ["parent_task_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 4. 更新 status CheckConstraint，新增 needs_clarification
    op.drop_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        "status IN ('queued','running','retrying','completed','partial','failed','cancelled','needs_clarification')",
    )

    # 5. 为新增字段建索引
    op.create_index(
        op.f("ix_analysis_tasks_clarification_status"),
        "analysis_tasks",
        ["clarification_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_analysis_tasks_parent_task_id"),
        "analysis_tasks",
        ["parent_task_id"],
        unique=False,
    )


def downgrade() -> None:
    # 删除索引
    op.drop_index(op.f("ix_analysis_tasks_parent_task_id"), table_name="analysis_tasks")
    op.drop_index(
        op.f("ix_analysis_tasks_clarification_status"), table_name="analysis_tasks"
    )

    # 恢复 status CheckConstraint
    op.drop_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        type_="check",
    )
    op.create_check_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        "status IN ('queued','running','retrying','completed','partial','failed','cancelled')",
    )

    # 删除追问链外键和字段
    op.drop_constraint(
        "fk_analysis_tasks_parent_task", "analysis_tasks", type_="foreignkey"
    )
    op.drop_column("analysis_tasks", "parent_task_id")
    op.drop_column("analysis_tasks", "resolved_question")
    op.drop_column("analysis_tasks", "clarification_missing_fields")
    op.drop_column("analysis_tasks", "clarification_status")

    # 删除时间戳字段
    op.drop_column("analysis_tasks", "completed_at")
    op.drop_column("analysis_tasks", "started_at")
