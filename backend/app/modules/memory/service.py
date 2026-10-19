"""Bounded planner-memory reads and report-derived memory writes."""

import json
from datetime import datetime, timedelta, timezone

from app.modules.memory.models import AnalysisMemory
from app.modules.memory.sources import MemorySource
from app.modules.organizations.models import CompanyMember
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.workflow.models import AnalysisTask
from sqlalchemy import or_
from sqlalchemy.orm import Session
from tiktoken import get_encoding

MAX_PLANNER_MEMORY_TOKENS = 1024
DEFAULT_MEMORY_TTL = timedelta(days=30)
PERSISTABLE_MEMORY_STATUSES = {"completed", "partial"}


def _planner_memory_payload(row: AnalysisMemory) -> dict:
    return {
        "memory_id": row.id,
        "source_task_id": row.source_task_id,
        "memory_type": row.memory_type,
        "content": row.content,
    }


def _memory_tokens(payload: dict) -> int:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return len(get_encoding("o200k_base").encode(text))


def select_planner_memories(
    db: Session,
    *,
    company_id: int | None,
    user_id: int,
    limit: int = 8,
    max_tokens: int = MAX_PLANNER_MEMORY_TOKENS,
) -> tuple[list[dict], dict]:
    """Select whole authorized memories and return a redacted selection manifest."""
    if limit <= 0:
        raise ValueError("limit must be greater than 0")
    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0")

    manifest = {
        "version": "planner-memory/v1",
        "limit": limit,
        "max_tokens": max_tokens,
        "selected_tokens": 0,
        "fragments": [],
    }
    if company_id is None:
        return [], manifest
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
        return [], manifest
    now = datetime.now(timezone.utc)
    rows = (
        db.query(AnalysisMemory)
        .join(MemorySource, AnalysisMemory.memory_source_id == MemorySource.id)
        .filter(
            AnalysisMemory.company_id == company_id,
            AnalysisMemory.user_id == user_id,
            AnalysisMemory.revoked.is_(False),
            or_(AnalysisMemory.expires_at.is_(None), AnalysisMemory.expires_at > now),
        )
        .order_by(AnalysisMemory.created_at.desc())
        .limit(limit + 1)
        .all()
    )
    selected: list[dict] = []
    for index, row in enumerate(rows):
        fragment = {
            "memory_id": row.id,
            "source_task_id": row.source_task_id,
            "decision": "omitted",
            "reason": "message_count_limit" if index >= limit else None,
            "selected_tokens": 0,
        }
        if index >= limit:
            manifest["fragments"].append(fragment)
            continue
        payload = _planner_memory_payload(row)
        tokens = _memory_tokens(payload)
        if manifest["selected_tokens"] + tokens > max_tokens:
            fragment["reason"] = "token_budget_exhausted"
            manifest["fragments"].append(fragment)
            continue
        selected.append(payload)
        manifest["selected_tokens"] += tokens
        fragment.update(
            {"decision": "selected", "reason": "within_budget", "selected_tokens": tokens}
        )
        manifest["fragments"].append(fragment)
    return selected, manifest


def planner_memories(
    db: Session, *, company_id: int | None, user_id: int, limit: int = 8
) -> list[dict]:
    """Compatibility wrapper for callers that only need bounded memory payloads."""
    memories, _ = select_planner_memories(
        db, company_id=company_id, user_id=user_id, limit=limit
    )
    return memories


def persist_report_memory(
    db: Session, *, task: AnalysisTask, report: FinalAnalysisReport
) -> AnalysisMemory | None:
    """Persist bounded, source-linked facts only after a report is published."""
    if (
        getattr(task, "company_id", None) is None
        or task.status not in PERSISTABLE_MEMORY_STATUSES
        or task.stage != "completed"
        or report.status != task.status
        or not report.confirmed_facts
    ):
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
        expires_at=datetime.now(timezone.utc) + DEFAULT_MEMORY_TTL,
    )
    db.add(memory)
    return memory
