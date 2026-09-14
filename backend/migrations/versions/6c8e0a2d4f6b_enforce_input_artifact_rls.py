"""enforce tenant RLS for input artifacts

Revision ID: 6c8e0a2d4f6b
Revises: 5b0a0b563d7f
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op


revision: str = "6c8e0a2d4f6b"
down_revision: Union[str, Sequence[str], None] = "5b0a0b563d7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    for table in (
        "input_artifacts",
        "input_artifact_versions",
        "artifact_processing_attempts",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    op.execute(
        f"""
        CREATE POLICY input_artifacts_tenant_scope ON input_artifacts
        USING (company_id = {_SCOPE})
        WITH CHECK (company_id = {_SCOPE})
        """
    )
    op.execute(
        f"""
        CREATE POLICY input_artifact_versions_tenant_scope
        ON input_artifact_versions
        USING (
            EXISTS (
                SELECT 1
                FROM input_artifacts AS artifact
                WHERE artifact.id = artifact_id
                  AND artifact.company_id = {_SCOPE}
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM input_artifacts AS artifact
                WHERE artifact.id = artifact_id
                  AND artifact.company_id = {_SCOPE}
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY artifact_processing_attempts_tenant_scope
        ON artifact_processing_attempts
        USING (
            EXISTS (
                SELECT 1
                FROM input_artifact_versions AS version
                JOIN input_artifacts AS artifact ON artifact.id = version.artifact_id
                WHERE version.id = artifact_version_id
                  AND artifact.company_id = {_SCOPE}
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM input_artifact_versions AS version
                JOIN input_artifacts AS artifact ON artifact.id = version.artifact_id
                WHERE version.id = artifact_version_id
                  AND artifact.company_id = {_SCOPE}
            )
        )
        """
    )


def downgrade() -> None:
    policies = (
        ("artifact_processing_attempts", "artifact_processing_attempts_tenant_scope"),
        ("input_artifact_versions", "input_artifact_versions_tenant_scope"),
        ("input_artifacts", "input_artifacts_tenant_scope"),
    )
    for table, policy in policies:
        op.execute(f"DROP POLICY {policy} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
