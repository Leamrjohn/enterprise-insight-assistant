"""Company-admin review endpoints for reports held before publication."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.company_auth import CurrentCompanyContext, require_admin
from app.db.session import get_db
from app.schemas.review_request import ReviewDecisionIn, ReviewDecisionOut
from app.services.outbox_service import publish_analysis_task_event
from app.services.review_service import approve_review_request, reject_review_request


router = APIRouter()


@router.post(
    "/review-requests/{request_id}/approve",
    response_model=ReviewDecisionOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def approve_review_request_endpoint(
    request_id: int,
    payload: ReviewDecisionIn,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        bundle = approve_review_request(
            db,
            request_id=request_id,
            company_id=context.company.id,
            reviewer=context.user,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if bundle is None:
        raise HTTPException(status_code=404, detail="review request not found")
    publish_analysis_task_event(db, event_id=bundle.outbox_event_id)
    return ReviewDecisionOut(
        task_id=bundle.task.id,
        status=bundle.task.status,
        review_status="approved",
    )


@router.post("/review-requests/{request_id}/reject", response_model=ReviewDecisionOut)
def reject_review_request_endpoint(
    request_id: int,
    payload: ReviewDecisionIn,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        task = reject_review_request(
            db,
            request_id=request_id,
            company_id=context.company.id,
            reviewer=context.user,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if task is None:
        raise HTTPException(status_code=404, detail="review request not found")
    return ReviewDecisionOut(
        task_id=task.id, status=task.status, review_status="rejected"
    )
