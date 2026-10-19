"""Company-admin review endpoints for reports held before publication."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.modules.organizations.access import CurrentCompanyContext, require_admin
from app.db.session import get_db
from app.modules.reviews.models import ReviewRequest
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.reviews.schemas import (
    ReviewDecisionIn,
    ReviewDecisionOut,
    ReviewRequestOut,
)
from app.modules.workflow.delivery.outbox import publish_analysis_task_event
from app.modules.reviews.service import approve_review_request, reject_review_request


router = APIRouter()


def _review_request_out(record: ReviewRequest) -> ReviewRequestOut:
    raw_draft = (record.task.result_data or {}).get("report_draft")
    report_draft = None
    draft_error = None
    if raw_draft is None:
        draft_error = "missing"
    else:
        try:
            report_draft = FinalAnalysisReport.model_validate(raw_draft)
        except ValidationError:
            draft_error = "invalid"
    return ReviewRequestOut.model_validate(
        {
            "id": record.id,
            "task_id": record.task_id,
            "task_question": record.task.question,
            "status": record.status,
            "reason_code": record.reason_code,
            "report_draft": report_draft,
            "draft_error": draft_error,
            "created_at": record.created_at,
        }
    )


@router.get("/review-requests", response_model=list[ReviewRequestOut])
def list_review_requests_endpoint(
    request_status: str = "pending",
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return only this company's review queue, newest first."""
    if request_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="invalid review request status")
    records = (
        db.query(ReviewRequest)
        .filter(
            ReviewRequest.company_id == context.company.id,
            ReviewRequest.status == request_status,
        )
        .order_by(ReviewRequest.created_at.desc(), ReviewRequest.id.desc())
        .all()
    )
    return [_review_request_out(record) for record in records]


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
    return ReviewDecisionOut.model_validate(
        {
            "task_id": bundle.task.id,
            "status": bundle.task.status,
            "review_status": "approved",
        }
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
    return ReviewDecisionOut.model_validate(
        {
            "task_id": task.id,
            "status": task.status,
            "review_status": "rejected",
        }
    )
