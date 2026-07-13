"""add status check constraint to analysis_tasks

Revision ID: 12385efc580f
Revises: f06252461745
Create Date: 2026-07-11 02:07:51.969113

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12385efc580f'
down_revision: Union[str, Sequence[str], None] = 'f06252461745'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "analysis_task_status",
        "analysis_tasks",
        sa.text("status IN ('queued', 'running', 'completed', 'failed', 'cancelled')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("analysis_task_status", "analysis_tasks")
