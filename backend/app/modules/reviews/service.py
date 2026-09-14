"""Deterministic human-review policy and approval state transitions."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.modules.workflow.models import AnalysisTask
from app.modules.reviews.models import ReviewRequest
from app.modules.identity.models import User
from app.modules.conversations.repository import get_assistant_message_by_task_id
from app.modules.workflow.outbox import create_analysis_task_event
from app.modules.reporting.schemas import FinalAnalysisReport


HIGH_RISK_REASON = "causal_hypothesis_requires_human_review"


@dataclass(frozen=True)
class ApprovedReviewBundle:
    task: AnalysisTask
    outbox_event_id: int


def requires_human_review(report: FinalAnalysisReport) -> bool:
    """Only a deterministic policy, never the Reviewer model, gates publishing."""
    return report.status == "completed" and bool(report.hypotheses)


def create_review_request(
    db: Session, *, task: AnalysisTask, reason_code: str = HIGH_RISK_REASON
) -> ReviewRequest:
    if task.company_id is None:
        raise ValueError("human review requires a company-scoped task")
    request = ReviewRequest(
        task_id=task.id,
        company_id=task.company_id,
        reason_code=reason_code,
    )
    db.add(request)
    return request


def approve_review_request(
    db: Session, *, request_id: int, company_id: int, reviewer: User, note: str | None
) -> ApprovedReviewBundle | None:
    request = (
        db.query(ReviewRequest)
        .filter(ReviewRequest.id == request_id, ReviewRequest.company_id == company_id)
        .first()
    )
    if request is None:
        return None
    task = db.get(AnalysisTask, request.task_id)
    if (
        task is None
        or request.status != "pending"
        or task.status != "awaiting_review"
        or task.company_id != company_id
    ):
        raise ValueError("review request is not awaiting approval")
    draft = (task.result_data or {}).get("report_draft")
    report = FinalAnalysisReport.model_validate(draft)
    if report.status != "completed":
        raise ValueError("only a completed report draft can be approved")

    now = datetime.now(timezone.utc)
    request.status = "approved"
    request.reviewer_id = reviewer.id
    request.decision_note = note
    request.reviewed_at = now
    task.status = "queued"
    task.stage = "queued"
    task.completed_at = None
    task.error_type = None
    task.error_message = None
    task.result_data = {**(task.result_data or {}), "review_publish_only": True}
    message = get_assistant_message_by_task_id(db, task_id=task.id)
    if message is not None:
        message.status = "queued"
        message.content = "审核已批准，正在发布已验证的报告。"
    event = create_analysis_task_event(db, task_id=task.id)
    db.commit()
    db.refresh(task)
    return ApprovedReviewBundle(task=task, outbox_event_id=event.id)


def reject_review_request(
    db: Session, *, request_id: int, company_id: int, reviewer: User, note: str | None
) -> AnalysisTask | None:
    request = (
        db.query(ReviewRequest)
        .filter(ReviewRequest.id == request_id, ReviewRequest.company_id == company_id)
        .first()
    )
    if request is None:
        return None
    task = db.get(AnalysisTask, request.task_id)
    if task is None or request.status != "pending" or task.status != "awaiting_review":
        raise ValueError("review request is not awaiting rejection")

    now = datetime.now(timezone.utc)
    request.status = "rejected"
    request.reviewer_id = reviewer.id
    request.decision_note = note
    request.reviewed_at = now
    task.status = "partial"
    task.stage = "completed"
    task.completed_at = now
    task.error_type = "human_review_rejected"
    task.error_message = "报告草稿未获人工批准，未发布正式结论。"
    task.result_summary = "人工审核未批准，本次仅保留草稿和审核意见。"
    task.result_data = {
        **(task.result_data or {}),
        "review_publish_only": False,
        "review": {"status": "rejected", "reason_code": request.reason_code},
    }
    message = get_assistant_message_by_task_id(db, task_id=task.id)
    if message is not None:
        message.status = "partial"
        message.content = task.result_summary
    db.commit()
    db.refresh(task)
    return task
