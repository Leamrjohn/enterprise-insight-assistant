"""Bounded planner-memory reads and report-derived memory writes."""

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.memory.models import AnalysisMemory
from app.modules.workflow.models import AnalysisTask
from app.modules.memory.sources import MemorySource
from app.modules.organizations.models import CompanyMember
from app.modules.reporting.schemas import FinalAnalysisReport


def planner_memories(
    db: Session, *, company_id: int | None, user_id: int, limit: int = 8
) -> list[dict]:
    """Return no memory if the task's user is no longer an approved member."""
    if company_id is None:
        return []
    active_member = (
        db.query(CompanyMember.id)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.user_id == user_id,
            CompanyMember.status == "approved",
        )
        .first()
    )
    if active_member is None:
        return []
    now = datetime.now(timezone.utc)
    rows = (
        db.query(AnalysisMemory)
        .filter(
            AnalysisMemory.company_id == company_id,
            AnalysisMemory.user_id == user_id,
            AnalysisMemory.revoked.is_(False),
            or_(AnalysisMemory.expires_at.is_(None), AnalysisMemory.expires_at > now),
        )
        .order_by(AnalysisMemory.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "memory_id": row.id,
            "source_task_id": row.source_task_id,
            "memory_type": row.memory_type,
            "content": row.content,
        }
        for row in rows
    ]


def persist_report_memory(
    db: Session, *, task: AnalysisTask, report: FinalAnalysisReport
) -> AnalysisMemory | None:
    """Persist only confirmed facts and limitations; never hypotheses or citations."""
    if getattr(task, "company_id", None) is None or report.status not in {
        "completed",
        "partial",
    }:
        return None
    idempotency_key = f"validated-report:{task.id}"
    source = (
        db.query(MemorySource)
        .filter(MemorySource.idempotency_key == idempotency_key)
        .first()
    )
    existing = (
        db.query(AnalysisMemory)
        .filter(AnalysisMemory.memory_source_id == source.id)
        .first()
        if source is not None
        else None
    )
    if existing is not None:
        return existing
    if source is None:
        source = MemorySource(
            company_id=task.company_id,
            source_task_id=task.id,
            source_type="validated_report",
            idempotency_key=idempotency_key,
        )
        db.add(source)
        db.flush()
    content = {
        "confirmed_facts": [fact.model_dump() for fact in report.confirmed_facts],
        "limitations": [limitation.model_dump() for limitation in report.limitations],
    }
    memory = AnalysisMemory(
        company_id=task.company_id,
        user_id=task.user_id,
        source_task_id=task.id,
        memory_source_id=source.id,
        memory_type="validated_report_facts",
        content=content,
    )
    db.add(memory)
    return memory
