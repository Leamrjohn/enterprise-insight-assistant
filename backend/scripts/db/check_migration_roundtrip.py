"""Migration round trip (E7a): upgrade head -> downgrade -1 -> upgrade head.

Fails when the newest migration cannot be undone, cannot be applied again after
being undone, or leaves a schema different from the first upgrade. It downgrades,
so it only runs against a database whose name ends in ``_test``.

Run from backend/: python scripts/db/check_migration_roundtrip.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def refuse_live_database(name: str) -> None:
    if not name.endswith("_test"):
        sys.exit(f"refused: {name!r} is not a *_test database; this check downgrades")


def schema_snapshot(engine: Engine) -> dict:
    inspector = inspect(engine)
    snapshot = {}
    for table in sorted(inspector.get_table_names()):
        if table == "alembic_version":
            continue
        snapshot[table] = {
            "columns": [
                (c["name"], str(c["type"]), c["nullable"], str(c.get("default")))
                for c in inspector.get_columns(table)
            ],
            "indexes": sorted(
                (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                for i in inspector.get_indexes(table)
            ),
            "foreign_keys": sorted(
                (
                    fk["name"] or "",
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                )
                for fk in inspector.get_foreign_keys(table)
            ),
            "unique": sorted(
                (u["name"] or "", tuple(u["column_names"]))
                for u in inspector.get_unique_constraints(table)
            ),
            "checks": sorted(
                (c["name"] or "", c["sqltext"])
                for c in inspector.get_check_constraints(table)
            ),
        }
    return snapshot


def _diff(before: dict, after: dict) -> list[str]:
    tables = before.keys() | after.keys()
    return sorted(t for t in tables if before.get(t) != after.get(t))


def check_roundtrip(cfg: Config, engine: Engine) -> list[str]:
    """Problems found; an empty list means the newest migration round-trips."""
    command.upgrade(cfg, "head")
    before = schema_snapshot(engine)
    try:
        command.downgrade(cfg, "-1")
    except Exception as exc:  # noqa: BLE001 - report, do not crash the check
        return [f"downgrade -1 failed: {type(exc).__name__}: {exc}"]
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001
        return [f"upgrade after downgrade failed: {type(exc).__name__}: {exc}"]
    after = schema_snapshot(engine)
    if before != after:
        return [
            f"schema differs after the round trip in tables: {_diff(before, after)}"
        ]
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--script-location", help="another migrations directory (to test the check)"
    )
    args = parser.parse_args()

    sys.path.insert(0, str(BACKEND_ROOT))
    from app.core.settings import get_settings
    from app.db.session import database_url

    refuse_live_database(get_settings().database_name)
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    if args.script_location:
        cfg.set_main_option("script_location", args.script_location)
    # The same role the migrations run as (migrations/env.py).
    user = os.getenv("MIGRATION_DATABASE_USER")
    engine = create_engine(database_url.set(username=user) if user else database_url)
    problems = check_roundtrip(cfg, engine)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)
    print("migration round trip ok")


if __name__ == "__main__":
    main()
