"""Operator command: the business configuration a task ran with (K4).

Read-only.  Prints the task's config snapshot hash, whether the stored hash
still matches the stored values, and every value that differs from the current
settings.  ``--all`` prints every snapshot value, not just the differences.

    python scripts/db/show_task_config.py 909
    python scripts/db/show_task_config.py 909 --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config.snapshot import build_config_snapshot, config_snapshot_hash
from app.db.session import SessionLocal
from app.modules.workflow.models import AnalysisTask
from sqlalchemy import text


def describe(task: AnalysisTask, *, show_all: bool = False) -> dict[str, Any]:
    snapshot = task.config_snapshot
    if not snapshot:
        return {
            "task_id": task.id,
            "config_snapshot": None,
            "note": "created before K4; it read the settings current at run time",
        }
    stored = snapshot.get("values") or {}
    current = build_config_snapshot()["values"]
    report: dict[str, Any] = {
        "task_id": task.id,
        "config_snapshot_hash": task.config_snapshot_hash,
        "hash_matches_values": task.config_snapshot_hash
        == config_snapshot_hash(snapshot),
        "snapshot_version": snapshot.get("version"),
        "differs_from_current": {
            name: {"task": stored.get(name), "current": current.get(name)}
            for name in sorted(set(stored) | set(current))
            if stored.get(name) != current.get(name)
        },
    }
    if show_all:
        report["values"] = stored
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id", type=int)
    parser.add_argument("--all", action="store_true", dest="show_all")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        task = db.get(AnalysisTask, args.task_id)
        if task is None:
            print(f"task {args.task_id} not found", file=sys.stderr)
            return 1
        print(
            json.dumps(
                describe(task, show_all=args.show_all), ensure_ascii=False, indent=2
            )
        )
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
