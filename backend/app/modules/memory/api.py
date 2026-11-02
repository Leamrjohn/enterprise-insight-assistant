"""Review memories: people decide what happens to a memory, never its content."""

from datetime import datetime
from typing import Literal

from app.db.session import get_db
from app.modules.memory.models import AnalysisMemory, MemoryAuditEvent
from app.modules.memory.service import (
    MemoryReview,
    MemoryTransitionError,
    flag_memory,
    review_memory,
)
from app.modules.organizations.access import (
    CurrentCompanyContext,
    get_current_company_context,
    require_admin,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

router = APIRouter()


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    source_task_id: int
    layer: str
    status: str
    content: dict
    confidence: float
    importance: float
    use_count: int
    last_used_at: datetime | None
    expires_at: datetime | None
    superseded_by_id: int | None
    created_at: datetime


class MemoryAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    original_memory_id: int
    action: str
    actor_kind: str
    actor_user_id: int | None
    reason: str | None
    details: dict
    created_at: datetime


class FlagRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReviewRequest(BaseModel):
    decision: Literal["restore", "revoke", "replace"]
    reason: str = Field(min_length=1, max_length=500)
    replacement_memory_id: int | None = None


def _is_admin(context: CurrentCompanyContext) -> bool:
    return context.role in {"owner", "admin"}


def _visible_memory(
    db: Session, memory_id: int, context: CurrentCompanyContext
) -> AnalysisMemory:
    """Another company's memory and a colleague's memory both look like not found."""
    memory = db.get(AnalysisMemory, memory_id)
    if (
        memory is None
        or memory.company_id != context.company.id
        or (not _is_admin(context) and memory.user_id != context.user.id)
    ):
        raise HTTPException(status_code=404, detail="memory not found")
    return memory


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(
    status: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=50, ge=1, le=200),
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    query = db.query(AnalysisMemory).filter(
        AnalysisMemory.company_id == context.company.id
    )
    if not _is_admin(context):
        query = query.filter(AnalysisMemory.user_id == context.user.id)
    if status is not None:
        query = query.filter(AnalysisMemory.status == status)
    return query.order_by(AnalysisMemory.id.desc()).limit(limit).all()


@router.get("/memories/{memory_id}/audit", response_model=list[MemoryAuditOut])
def list_memory_audit(
    memory_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    memory = _visible_memory(db, memory_id, context)
    return (
        db.query(MemoryAuditEvent)
        .filter(
            MemoryAuditEvent.company_id == context.company.id,
            MemoryAuditEvent.original_memory_id == memory.id,
        )
        .order_by(MemoryAuditEvent.id)
        .all()
    )


@router.post("/memories/{memory_id}/flag", response_model=MemoryOut)
def flag(
    memory_id: int,
    request: FlagRequest,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    memory = _visible_memory(db, memory_id, context)
    try:
        flag_memory(
            db,
            memory,
            actor_kind="user",
            actor_user_id=context.user.id,
            reason=request.reason,
        )
    except MemoryTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    db.commit()
    return memory


@router.post("/memories/{memory_id}/review", response_model=MemoryOut)
def review(
    memory_id: int,
    request: ReviewRequest,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    memory = _visible_memory(db, memory_id, context)
    try:
        review_memory(
            db,
            memory,
            MemoryReview(
                decision=request.decision,
                reason=request.reason,
                reviewer_user_id=context.user.id,
                replacement_memory_id=request.replacement_memory_id,
            ),
        )
    except MemoryTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    db.commit()
    return memory
