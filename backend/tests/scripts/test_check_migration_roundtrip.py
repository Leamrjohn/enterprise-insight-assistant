import sys
import textwrap
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/db"))

from check_migration_roundtrip import check_roundtrip, refuse_live_database

ENV_PY = """
from alembic import context
from sqlalchemy import create_engine

with create_engine(context.config.get_main_option("sqlalchemy.url")).connect() as c:
    context.configure(connection=c)
    with context.begin_transaction():
        context.run_migrations()
"""

FIRST = """
revision = "r1"
down_revision = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table("a", sa.Column("id", sa.Integer, primary_key=True))


def downgrade():
    op.drop_table("a")
"""

SECOND = """
revision = "r2"
down_revision = "r1"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table("b", sa.Column("id", sa.Integer, primary_key=True))
    op.create_index("ix_b_id", "b", ["id"])


def downgrade():
{downgrade}
"""


def _alembic(tmp_path, downgrade: str) -> tuple[Config, object]:
    scripts = tmp_path / "migrations"
    (scripts / "versions").mkdir(parents=True)
    (scripts / "env.py").write_text(ENV_PY, encoding="utf-8")
    (scripts / "script.py.mako").write_text("", encoding="utf-8")
    (scripts / "versions" / "r1.py").write_text(FIRST, encoding="utf-8")
    (scripts / "versions" / "r2.py").write_text(
        SECOND.format(downgrade=textwrap.indent(downgrade, "    ")), encoding="utf-8"
    )
    url = f"sqlite:///{tmp_path / 'db.sqlite'}"
    cfg = Config()
    cfg.set_main_option("script_location", str(scripts))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg, create_engine(url)


def test_a_reversible_migration_passes(tmp_path):
    cfg, engine = _alembic(
        tmp_path, 'op.drop_index("ix_b_id", "b")\nop.drop_table("b")'
    )

    assert check_roundtrip(cfg, engine) == []


def test_a_downgrade_that_does_nothing_fails(tmp_path):
    # Upgrading again then hits "table b already exists".
    cfg, engine = _alembic(tmp_path, "pass")

    [problem] = check_roundtrip(cfg, engine)

    assert problem.startswith("upgrade after downgrade failed")


def test_a_downgrade_that_raises_fails(tmp_path):
    cfg, engine = _alembic(tmp_path, 'raise NotImplementedError("one-way")')

    [problem] = check_roundtrip(cfg, engine)

    assert problem.startswith("downgrade -1 failed")


def test_a_downgrade_that_leaves_the_schema_different_fails(tmp_path):
    # The downgrade leaves a table behind, so re-upgrading works but the schema
    # is no longer the one the first upgrade produced.
    cfg, engine = _alembic(
        tmp_path,
        'op.drop_index("ix_b_id", "b")\nop.drop_table("b")\n'
        'op.create_table("leftover", sa.Column("id", sa.Integer, primary_key=True))',
    )

    [problem] = check_roundtrip(cfg, engine)

    assert problem.startswith("schema differs after the round trip")
    assert "leftover" in problem


@pytest.mark.parametrize("name", ["agent_platform", "agent_platform_prod", ""])
def test_refuse_live_database(name):
    with pytest.raises(SystemExit):
        refuse_live_database(name)


def test_allow_a_test_database():
    refuse_live_database("agent_platform_test")
