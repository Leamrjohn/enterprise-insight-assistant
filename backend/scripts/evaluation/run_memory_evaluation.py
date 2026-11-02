"""Memory selection baseline over fixed scenarios, using the real selector.

Writes the fixture memories into the isolated test database inside one
transaction, asks the production selector what it would give the Planner, and
rolls everything back.  No model is called.

Run (evaluation container, agent_platform_test):
    python -m scripts.evaluation.run_memory_evaluation
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db.session import engine, set_tenant_scope
from app.main import app  # noqa: F401 - registers every model for the mapper
from app.modules.evaluation.memory_selection import (
    score_memory_case,
    summarize_memory_cases,
)
from app.modules.identity.models import User
from app.modules.memory.models import AnalysisMemory
from app.modules.memory.service import select_planner_memories
from app.modules.memory.sources import MemorySource
from app.modules.organizations.models import Company, CompanyMember
from app.modules.workflow.models import AnalysisTask
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    BACKEND_ROOT
    / "tests"
    / "fixtures"
    / "evaluation_memory"
    / "memory_scenarios_v1.json"
)
EXPECTED_DATABASE = "agent_platform_test"
ISOLATION_KEYS = frozenset({"other-company", "other-user"})


def _add_member(db: Session, *, name: str, company: Company) -> User:
    user = User(name=name, api_key=f"{name}-key")
    db.add(user)
    db.flush()
    db.add(
        CompanyMember(
            user_id=user.id, company_id=company.id, role="owner", status="approved"
        )
    )
    db.flush()
    return user


def _add_memory(
    db: Session, *, item: dict, company: Company, user: User, now: datetime
) -> int:
    set_tenant_scope(db, company.id)
    task = AnalysisTask(
        user_id=user.id,
        company_id=company.id,
        question="memory evaluation",
        status="completed",
        stage="completed",
    )
    db.add(task)
    db.flush()
    source = MemorySource(
        company_id=company.id,
        source_task_id=task.id,
        source_type="validated_report",
        idempotency_key=f"memory-evaluation:{task.id}",
    )
    db.add(source)
    db.flush()
    created = now - timedelta(days=item["age_days"])
    memory = AnalysisMemory(
        company_id=company.id,
        user_id=user.id,
        source_task_id=task.id,
        memory_source_id=source.id,
        memory_type="validated_report_facts",
        content={"confirmed_facts": [{"text": item["fact"]}]},
        # Flagged, superseded and business validity have no column yet, so the
        # baseline stores them as ordinary memories.
        expires_at=created + timedelta(days=30),
        revoked=item["status"] == "revoked",
        created_at=created,
    )
    db.add(memory)
    db.flush()
    return memory.id


def main() -> None:
    if engine.url.database != EXPECTED_DATABASE:
        sys.exit(f"refusing to run outside {EXPECTED_DATABASE}")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        company = Company(name="memory-evaluation")
        other_company = Company(name="memory-evaluation-other")
        db.add_all([company, other_company])
        db.flush()
        owner = _add_member(db, name="memory-owner", company=company)
        colleague = _add_member(db, name="memory-colleague", company=company)
        outsider = _add_member(db, name="memory-outsider", company=other_company)
        placements = {
            "self": (company, owner),
            "other_user": (company, colleague),
            "other_company": (other_company, outsider),
        }
        now = datetime.now(timezone.utc)
        keys_by_id = {}
        for item in fixture["memories"]:
            target_company, target_user = placements[item["owner"]]
            memory_id = _add_memory(
                db, item=item, company=target_company, user=target_user, now=now
            )
            keys_by_id[memory_id] = item["key"]
        set_tenant_scope(db, company.id)
        rows = []
        for case in fixture["cases"]:
            payloads, _ = select_planner_memories(
                db, company_id=company.id, user_id=owner.id
            )
            selected = {keys_by_id[p["memory_id"]] for p in payloads}
            score = score_memory_case(
                selected=selected,
                must_select=case["must_select"],
                must_not_select=case["must_not_select"],
            )
            rows.append(
                {
                    **score,
                    "case_id": case["case_id"],
                    "split": case["split"],
                    "found": sorted(set(case["must_select"]) & selected),
                    "isolation_violations": sorted(selected & ISOLATION_KEYS),
                }
            )
    finally:
        db.close()
        transaction.rollback()
        connection.close()
    print(
        json.dumps(
            {
                "selector": "select_planner_memories",
                **summarize_memory_cases(rows),
                "results": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
