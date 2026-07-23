"""add conversations and task links

Revision ID: a3b7c9d1e2f4
Revises: 60ca3f1d5096
Create Date: 2026-07-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a3b7c9d1e2f4"
down_revision: Union[str, Sequence[str], None] = "60ca3f1d5096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversations_user_id"),
        "conversations",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("analysis_task_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name=op.f("ck_conversation_messages_role_values"),
        ),
        sa.CheckConstraint(
            "status IN ("
            "'queued', 'running', 'completed', 'partial', 'failed', 'cancelled'"
            ")",
            name=op.f("ck_conversation_messages_status_values"),
        ),
        sa.CheckConstraint(
            "analysis_task_id IS NULL OR role = 'assistant'",
            name=op.f("ck_conversation_messages_task_only_for_assistant"),
        ),
        sa.ForeignKeyConstraint(
            ["analysis_task_id"],
            ["analysis_tasks.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_task_id"),
    )
    op.create_index(
        op.f("ix_conversation_messages_conversation_id"),
        "conversation_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_messages_status"),
        "conversation_messages",
        ["status"],
        unique=False,
    )

    op.add_column(
        "analysis_tasks",
        sa.Column("conversation_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column("input_message_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "context_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_analysis_tasks_conversation_id"),
        "analysis_tasks",
        ["conversation_id"],
        unique=False,
    )
    op.create_unique_constraint(
        op.f("uq_analysis_tasks_input_message_id"),
        "analysis_tasks",
        ["input_message_id"],
    )
    op.create_foreign_key(
        op.f("fk_analysis_tasks_conversation_id_conversations"),
        "analysis_tasks",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_analysis_tasks_input_message_id_conversation_messages"),
        "analysis_tasks",
        "conversation_messages",
        ["input_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_analysis_tasks_input_message_id_conversation_messages"),
        "analysis_tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_analysis_tasks_conversation_id_conversations"),
        "analysis_tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("uq_analysis_tasks_input_message_id"),
        "analysis_tasks",
        type_="unique",
    )
    op.drop_index(
        op.f("ix_analysis_tasks_conversation_id"),
        table_name="analysis_tasks",
    )
    op.drop_column("analysis_tasks", "context_snapshot")
    op.drop_column("analysis_tasks", "input_message_id")
    op.drop_column("analysis_tasks", "conversation_id")
    op.drop_index(
        op.f("ix_conversation_messages_status"),
        table_name="conversation_messages",
    )
    op.drop_index(
        op.f("ix_conversation_messages_conversation_id"),
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_table("conversations")
