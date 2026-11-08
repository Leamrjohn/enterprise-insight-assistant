"""add human review request persistence and awaiting-review task state

Revision ID: g4a5b6c7d8e9
Revises: f3a4b5c6d7e8
"""

from alembic import op
import sqlalchemy as sa


revision = "g4a5b6c7d8e9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_analysis_tasks_analysistask_status_values", "analysis_tasks")
    op.drop_constraint(
        "ck_analysis_tasks_analysistask_task_stage_values", "analysis_tasks"
    )
    op.create_check_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        "status IN ('queued','running','retrying','awaiting_review','completed','partial','failed','cancelled','needs_clarification')",
    )
    op.create_check_constraint(
        "analysistask_task_stage_values",
        "analysis_tasks",
        "stage IN ('queued','planning','querying_data','retrieving_knowledge','composing_report','saving_result','awaiting_review','retrying','completed')",
    )
    op.create_table(
        "review_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("reviewer_id", sa.Integer()),
        sa.Column("decision_note", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="review_request_status_values",
        ),
        sa.ForeignKeyConstraint(["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_review_requests_company_id", "review_requests", ["company_id"])
    op.create_index("ix_review_requests_status", "review_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_review_requests_status", table_name="review_requests")
    op.drop_index("ix_review_requests_company_id", table_name="review_requests")
    op.drop_table("review_requests")
    op.drop_constraint("ck_analysis_tasks_analysistask_status_values", "analysis_tasks")
    op.drop_constraint(
        "ck_analysis_tasks_analysistask_task_stage_values", "analysis_tasks"
    )
    op.create_check_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        "status IN ('queued','running','retrying','completed','partial','failed','cancelled','needs_clarification')",
    )
    op.create_check_constraint(
        "analysistask_task_stage_values",
        "analysis_tasks",
        "stage IN ('queued','planning','querying_data','retrieving_knowledge','composing_report','saving_result','retrying','completed')",
    )
