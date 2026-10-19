"""freeze input artifact versions for analysis tasks

Revision ID: e8f9a0b1c2d3
Revises: c9e4a1f7b2d8
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "c9e4a1f7b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLE = "analysis_task_input_artifact_versions"
_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("artifact_version_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name="position_non_negative"),
        sa.ForeignKeyConstraint(
            ["task_id"], ["analysis_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"],
            ["input_artifact_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("task_id", "artifact_version_id"),
        sa.UniqueConstraint("task_id", "position", name="uq_task_input_artifact_position"),
    )
    op.create_index(
        "ix_task_input_artifact_versions_artifact_version_id",
        _TABLE,
        ["artifact_version_id"],
    )
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY analysis_task_input_artifact_versions_tenant_scope
        ON {_TABLE}
        USING (
            EXISTS (
                SELECT 1
                FROM analysis_tasks AS task
                JOIN input_artifact_versions AS version
                  ON version.id = artifact_version_id
                JOIN input_artifacts AS artifact
                  ON artifact.id = version.artifact_id
                WHERE task.id = task_id
                  AND task.company_id = {_SCOPE}
                  AND artifact.company_id = {_SCOPE}
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM analysis_tasks AS task
                JOIN input_artifact_versions AS version
                  ON version.id = artifact_version_id
                JOIN input_artifacts AS artifact
                  ON artifact.id = version.artifact_id
                WHERE task.id = task_id
                  AND task.company_id = {_SCOPE}
                  AND artifact.company_id = {_SCOPE}
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY analysis_task_input_artifact_versions_tenant_scope ON " + _TABLE
    )
    op.execute(f"ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_task_input_artifact_versions_artifact_version_id", table_name=_TABLE
    )
    op.drop_table(_TABLE)
