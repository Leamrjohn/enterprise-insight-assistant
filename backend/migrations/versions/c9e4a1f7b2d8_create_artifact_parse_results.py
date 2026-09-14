"""create immutable artifact parse results

Revision ID: c9e4a1f7b2d8
Revises: a7f3c9e1b6d2
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c9e4a1f7b2d8"
down_revision: str | Sequence[str] | None = "a7f3c9e1b6d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RESULT_TABLE = "artifact_parse_results"
_VERSION_TABLE = "input_artifact_versions"
_ATTEMPT_TABLE = "artifact_processing_attempts"
_SCOPE = "NULLIF(current_setting('app.company_id', true), '')::integer"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_artifact_processing_attempt_id_version",
        _ATTEMPT_TABLE,
        ["id", "artifact_version_id"],
    )
    op.create_table(
        _RESULT_TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_version_id", sa.Integer(), nullable=False),
        sa.Column("processing_attempt_id", sa.Integer(), nullable=False),
        sa.Column("result_schema_version", sa.String(length=64), nullable=False),
        sa.Column("manifest_object_key", sa.String(length=512), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("extracted_text_object_key", sa.String(length=512), nullable=True),
        sa.Column("extracted_text_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "extracted_text_char_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(btrim(result_schema_version)) BETWEEN 1 AND 64",
            name="ck_artifact_parse_result_schema_version",
        ),
        sa.CheckConstraint(
            "length(btrim(manifest_object_key)) BETWEEN 1 AND 512",
            name="ck_artifact_parse_result_manifest_object_key",
        ),
        sa.CheckConstraint(
            "manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_artifact_parse_result_manifest_sha256",
        ),
        sa.CheckConstraint(
            "extracted_text_char_count >= 0",
            name="ck_artifact_parse_result_extracted_text_char_count",
        ),
        sa.CheckConstraint(
            "(extracted_text_object_key IS NULL "
            "AND extracted_text_sha256 IS NULL "
            "AND extracted_text_char_count = 0) "
            "OR (extracted_text_object_key IS NOT NULL "
            "AND extracted_text_sha256 IS NOT NULL)",
            name="ck_artifact_parse_result_extracted_text_fields",
        ),
        sa.CheckConstraint(
            "extracted_text_object_key IS NULL "
            "OR length(btrim(extracted_text_object_key)) BETWEEN 1 AND 512",
            name="ck_artifact_parse_result_extracted_text_object_key",
        ),
        sa.CheckConstraint(
            "extracted_text_sha256 IS NULL "
            "OR extracted_text_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_artifact_parse_result_extracted_text_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"],
            [f"{_VERSION_TABLE}.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["processing_attempt_id", "artifact_version_id"],
            [f"{_ATTEMPT_TABLE}.id", f"{_ATTEMPT_TABLE}.artifact_version_id"],
            name="fk_artifact_parse_result_attempt_same_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "processing_attempt_id",
            name="uq_artifact_parse_result_processing_attempt",
        ),
        sa.UniqueConstraint(
            "id",
            "artifact_version_id",
            name="uq_artifact_parse_result_id_version",
        ),
    )
    op.create_index(
        "ix_artifact_parse_results_artifact_version_id",
        _RESULT_TABLE,
        ["artifact_version_id"],
    )
    op.create_index(
        "ix_artifact_parse_results_processing_attempt_id",
        _RESULT_TABLE,
        ["processing_attempt_id"],
    )

    op.add_column(
        _VERSION_TABLE,
        sa.Column("active_parse_result_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_input_artifact_versions_active_parse_result_id",
        _VERSION_TABLE,
        ["active_parse_result_id"],
    )
    op.create_foreign_key(
        "fk_input_artifact_version_active_parse_result_same_version",
        _VERSION_TABLE,
        _RESULT_TABLE,
        ["active_parse_result_id", "id"],
        ["id", "artifact_version_id"],
        ondelete="RESTRICT",
    )

    op.execute(f"ALTER TABLE {_RESULT_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_RESULT_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY artifact_parse_results_tenant_scope
        ON {_RESULT_TABLE}
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
    op.execute(
        "DROP POLICY artifact_parse_results_tenant_scope ON " + _RESULT_TABLE
    )
    op.execute(f"ALTER TABLE {_RESULT_TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_RESULT_TABLE} DISABLE ROW LEVEL SECURITY")
    op.drop_constraint(
        "fk_input_artifact_version_active_parse_result_same_version",
        _VERSION_TABLE,
        type_="foreignkey",
    )
    op.drop_index(
        "ix_input_artifact_versions_active_parse_result_id",
        table_name=_VERSION_TABLE,
    )
    op.drop_column(_VERSION_TABLE, "active_parse_result_id")
    op.drop_table(_RESULT_TABLE)
    op.drop_constraint(
        "uq_artifact_processing_attempt_id_version",
        _ATTEMPT_TABLE,
        type_="unique",
    )
