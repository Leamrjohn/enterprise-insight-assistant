"""Bounded planner-memory reads, report-derived writes and the memory lifecycle."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config.memory import MemoryConfig
from app.core.config.snapshot import runtime_settings
from app.core.tokenizer import count_tokens
from app.modules.documents.search_tokens import jieba_tokens
from app.modules.memory.models import AnalysisMemory, MemoryAuditEvent
from app.modules.memory.sources import MemorySource
from app.modules.organizations.models import CompanyMember
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.workflow.models import AnalysisTask
from sqlalchemy import or_
from sqlalchemy.orm import Session

# Defaults only; the running values come from MEMORY_* settings (K1).
DEFAULT_MEMORY_TTL = timedelta(
    days=MemoryConfig.model_fields["memory_ttl_days"].default
)
PERSISTABLE_MEMORY_STATUSES = {"completed", "partial"}
MIN_RELEVANCE = 0.3
RECENCY_HALF_LIFE_DAYS = 90
MIN_RECENCY = 0.25
_IDENTIFYING_TOKEN = re.compile(r"\d{3,}")
_YEAR_TOKEN = re.compile(r"20\d{2}")
_NOT_A_WORD = re.compile(r"[^\w]+")


class MemoryTransitionError(ValueError):
    """The requested change is not allowed from the memory's current status."""


def _planner_memory_payload(row: AnalysisMemory) -> dict:
    return {
        "memory_id": row.id,
        "source_task_id": row.source_task_id,
        "memory_type": row.memory_type,
        "content": row.content,
    }


def _memory_tokens(payload: dict) -> int:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return count_tokens(text)


def _facts_text(row: AnalysisMemory) -> str:
    facts = (row.content or {}).get("confirmed_facts") or []
    return " ".join(str(fact.get("statement", "")) for fact in facts)


def _token_weight(token: str) -> int:
    """A customer or supplier number says far more than a common word or a year."""
    if _IDENTIFYING_TOKEN.search(token) and not _YEAR_TOKEN.fullmatch(token):
        return 3
    return 1


def memory_relevance(question: str, text: str) -> float:
    """Share of the question's weighted words that the memory also contains."""
    wanted = set(jieba_tokens(question))
    if not wanted:
        return 0.0
    found = wanted & set(jieba_tokens(text))
    return sum(map(_token_weight, found)) / sum(map(_token_weight, wanted))


def _recency(created_at: datetime, now: datetime) -> float:
    age_days = max((now - created_at).total_seconds() / 86400, 0)
    return max(0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS), MIN_RECENCY)


def select_planner_memories(
    db: Session,
    *,
    company_id: int | None,
    user_id: int,
    question: str | None = None,
    limit: int = 8,
    max_tokens: int | None = None,
    record_use: bool = False,
) -> tuple[list[dict], dict]:
    if max_tokens is None:
        max_tokens = runtime_settings().memory_planner_max_tokens
    """Select whole authorized memories and return a redacted selection manifest.

    Code decides what may be used: company, user, status and both kinds of expiry
    are hard filters.  Only then does relevance rank what is left, and without a
    question the newest come first.
    """
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
    query = (
        db.query(AnalysisMemory)
        .join(MemorySource, AnalysisMemory.memory_source_id == MemorySource.id)
        .filter(
            AnalysisMemory.company_id == company_id,
            AnalysisMemory.user_id == user_id,
            AnalysisMemory.status == "active",
            AnalysisMemory.revoked.is_(False),
            or_(AnalysisMemory.expires_at.is_(None), AnalysisMemory.expires_at > now),
            or_(
                AnalysisMemory.business_valid_until.is_(None),
                AnalysisMemory.business_valid_until >= now.date(),
            ),
        )
        .order_by(AnalysisMemory.created_at.desc())
    )
    if question is None:
        rows = query.limit(limit + 1).all()
    else:
        scored = []
        for row in query.all():
            relevance = memory_relevance(question, _facts_text(row))
            if relevance < MIN_RELEVANCE:
                continue
            score = (
                relevance
                * _recency(row.created_at, now)
                * row.importance
                * row.confidence
            )
            scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        rows = [row for _, row in scored[: limit + 1]]

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
            {
                "decision": "selected",
                "reason": "within_budget",
                "selected_tokens": tokens,
            }
        )
        manifest["fragments"].append(fragment)
        if record_use:
            row.last_used_at = now
            row.use_count += 1
    return selected, manifest


def planner_memories(
    db: Session, *, company_id: int | None, user_id: int, limit: int = 8
) -> list[dict]:
    """Compatibility wrapper for callers that only need bounded memory payloads."""
    memories, _ = select_planner_memories(
        db, company_id=company_id, user_id=user_id, limit=limit
    )
    return memories


def _audit(
    db: Session,
    memory: AnalysisMemory,
    *,
    action: str,
    actor_kind: str,
    actor_user_id: int | None = None,
    reason: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        MemoryAuditEvent(
            company_id=memory.company_id,
            memory_id=memory.id,
            original_memory_id=memory.id,
            action=action,
            actor_kind=actor_kind,
            actor_user_id=actor_user_id,
            reason=reason,
            details=details or {},
        )
    )


def subject_key_for(question: str) -> str:
    """The same question asked again is about the same subject."""
    normalized = _NOT_A_WORD.sub("", question).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def persist_report_memory(
    db: Session, *, task: AnalysisTask, report: FinalAnalysisReport
) -> AnalysisMemory | None:
    """Persist bounded, source-linked facts only after a report is published.

    A newer report on the same subject replaces the older memory.  One saying the
    same thing only extends the old memory's retention.
    """
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
    content = {
        "confirmed_facts": [fact.model_dump() for fact in report.confirmed_facts],
        "limitations": [limitation.model_dump() for limitation in report.limitations],
    }
    subject_key = subject_key_for(task.question or "")
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=runtime_settings().memory_ttl_days
    )
    previous = (
        db.query(AnalysisMemory)
        .filter(
            AnalysisMemory.company_id == task.company_id,
            AnalysisMemory.user_id == task.user_id,
            AnalysisMemory.subject_key == subject_key,
            AnalysisMemory.status == "active",
        )
        .order_by(AnalysisMemory.id.desc())
        .with_for_update()
        .first()
    )
    if previous is not None and _same_facts(previous.content, content):
        previous.expires_at = expires_at
        _audit(
            db,
            previous,
            action="duplicate_ignored",
            actor_kind="system",
            details={"source_task_id": task.id},
        )
        return previous
    if source is None:
        source = MemorySource(
            company_id=task.company_id,
            source_task_id=task.id,
            source_type="validated_report",
            idempotency_key=idempotency_key,
        )
        db.add(source)
        db.flush()
    memory = AnalysisMemory(
        company_id=task.company_id,
        user_id=task.user_id,
        source_task_id=task.id,
        memory_source_id=source.id,
        memory_type="validated_report_facts",
        layer="fact",
        content=content,
        subject_key=subject_key,
        confidence=0.9 if report.status == "completed" else 0.6,
        expires_at=expires_at,
    )
    db.add(memory)
    db.flush()
    _audit(
        db,
        memory,
        action="created",
        actor_kind="system",
        details={"source_task_id": task.id},
    )
    if previous is not None:
        previous.status = "superseded"
        previous.superseded_by_id = memory.id
        _audit(
            db,
            previous,
            action="superseded",
            actor_kind="system",
            details={"replaced_by": memory.id},
        )
    return memory


def _same_facts(left: dict, right: dict) -> bool:
    def statements(content: dict) -> list[str]:
        return sorted(
            str(fact.get("statement")) for fact in content.get("confirmed_facts") or []
        )

    return statements(left) == statements(right)


def flag_memory(
    db: Session,
    memory: AnalysisMemory,
    *,
    actor_kind: str,
    reason: str,
    actor_user_id: int | None = None,
) -> None:
    """Stop using a memory until a person looks at it; nothing is removed yet."""
    if memory.status != "active":
        raise MemoryTransitionError(f"cannot flag a memory in status {memory.status}")
    memory.status = "flagged"
    _audit(
        db,
        memory,
        action="flagged",
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
        reason=reason,
    )


def flag_memories_from_model(
    db: Session, *, company_id: int, flags: list[dict], allowed_ids: set[int]
) -> list[int]:
    """Apply a model's suspicions, only to memories this task really used."""
    flagged = []
    for item in flags:
        memory_id = item.get("memory_id")
        if memory_id not in allowed_ids:
            continue
        memory = db.get(AnalysisMemory, memory_id)
        if (
            memory is None
            or memory.company_id != company_id
            or memory.status != "active"
        ):
            continue
        flag_memory(
            db,
            memory,
            actor_kind="model",
            reason=str(item.get("reason") or "")[:500],
        )
        flagged.append(memory.id)
    return flagged


@dataclass(frozen=True)
class MemoryReview:
    decision: str  # restore, revoke or replace
    reason: str
    reviewer_user_id: int
    replacement_memory_id: int | None = None


def review_memory(db: Session, memory: AnalysisMemory, review: MemoryReview) -> None:
    """A person's decision on a flagged memory.

    A replacement must be another active memory: people decide which memory is
    right, but only validated reports can put new facts into memory.
    """
    if memory.status != "flagged":
        raise MemoryTransitionError("only a flagged memory can be reviewed")
    details: dict = {}
    if review.decision == "restore":
        memory.status = "active"
    elif review.decision == "revoke":
        memory.status = "revoked"
        memory.revoked = True
    elif review.decision == "replace":
        replacement = (
            db.get(AnalysisMemory, review.replacement_memory_id)
            if review.replacement_memory_id is not None
            else None
        )
        if (
            replacement is None
            or replacement.id == memory.id
            or replacement.company_id != memory.company_id
            or replacement.status != "active"
        ):
            raise MemoryTransitionError("replacement must be an active memory")
        memory.status = "superseded"
        memory.superseded_by_id = replacement.id
        details["replaced_by"] = replacement.id
    else:
        raise MemoryTransitionError(f"unknown decision {review.decision}")
    _audit(
        db,
        memory,
        action=f"review_{review.decision}",
        actor_kind="user",
        actor_user_id=review.reviewer_user_id,
        reason=review.reason,
        details=details,
    )


def cleanup_memories(
    db: Session, *, company_id: int, now: datetime | None = None
) -> dict[str, int]:
    """Soft-delete what has outlived retention, then purge what was deleted long ago.

    A flagged memory waits for its review even if it expires, so that a pending
    decision is not lost to the calendar.
    """
    now = now or datetime.now(timezone.utc)
    expired = (
        db.query(AnalysisMemory)
        .filter(
            AnalysisMemory.company_id == company_id,
            AnalysisMemory.status.in_(("active", "superseded", "revoked")),
            or_(
                AnalysisMemory.expires_at <= now,
                AnalysisMemory.business_valid_until < now.date(),
            ),
        )
        .all()
    )
    for memory in expired:
        previous_status = memory.status
        memory.status = "deleted"
        memory.deleted_at = now
        _audit(
            db,
            memory,
            action="soft_deleted",
            actor_kind="system",
            details={"previous_status": previous_status},
        )
    purge_before = now - timedelta(
        days=runtime_settings().memory_soft_delete_retention_days
    )
    purgeable = (
        db.query(AnalysisMemory)
        .filter(
            AnalysisMemory.company_id == company_id,
            AnalysisMemory.status == "deleted",
            AnalysisMemory.deleted_at <= purge_before,
        )
        .all()
    )
    for memory in purgeable:
        _audit(db, memory, action="purged", actor_kind="system")
        db.flush()
        db.delete(memory)
    db.flush()
    return {"soft_deleted": len(expired), "purged": len(purgeable)}
