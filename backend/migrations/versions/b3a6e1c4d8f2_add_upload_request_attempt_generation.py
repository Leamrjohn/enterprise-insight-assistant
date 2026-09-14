"""add upload request attempt generation

Revision ID: b3a6e1c4d8f2
Revises: 94601698eefd
Create Date: 2026-09-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3a6e1c4d8f2"
down_revision: Union[str, Sequence[str], None] = "94601698eefd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "input_artifact_upload_requests",
        sa.Column(
            "attempt_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_check_constraint(
        op.f("ck_input_upload_request_attempt_generation"),
        "input_artifact_upload_requests",
        "attempt_generation > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_input_upload_request_attempt_generation"),
        "input_artifact_upload_requests",
        type_="check",
    )
    op.drop_column("input_artifact_upload_requests", "attempt_generation")
