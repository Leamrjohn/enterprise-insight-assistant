"""allow partial analysis task status

Revision ID: 60ca3f1d5096
Revises: 43a749220e4a
Create Date: 2026-07-21 23:16:49.366595

"""
from typing import Sequence, Union

from alembic import op
revision: str = "60ca3f1d5096"
down_revision: Union[str, Sequence[str], None] = "43a749220e4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.drop_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        type_="check",
    )

    op.create_check_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        "status IN ("
        "'queued', 'running', 'retrying', 'completed', "
        "'partial', 'failed', 'cancelled'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        type_="check",
    )

    op.create_check_constraint(
        "analysistask_status_values",
        "analysis_tasks",
        "status IN ("
        "'queued', 'running', 'retrying', 'completed', "
        "'failed', 'cancelled'"
        ")",
    )
