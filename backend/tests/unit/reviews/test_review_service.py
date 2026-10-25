import pytest
from app.db.session import set_tenant_scope
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.organizations.models import Company
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.reporting.validation import ReportValidationError
from app.modules.reviews.models import ReviewRequest
from app.modules.reviews.service import approve_review_request, reject_review_request
from app.modules.workflow.delivery.outbox import create_analysis_task_event
from app.modules.workflow.delivery.outbox_models import AnalysisTaskOutboxEvent
from app.modules.workflow.lifecycle.execution import claim_execution
from app.modules.workflow.models import AnalysisTask, AnalysisTaskDocument
from app.modules.workflow.tasks import _publish_approved_draft


def _completed_draft(*, chunk_id: int) -> dict:
    return {
        "status": "completed",
        "executive_summary": "已确认销售下降，待审核可能原因。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "销售额下降。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "可能原因（未证实）：客户减少采购。",
                "related_fact_ids": ["fact-1"],
                "citation_chunk_ids": [chunk_id],
                "support_level": "low",
            }
        ],
        "recommendations": [
            {
                "recommendation_id": "recommendation-1",
                "priority": "medium",
                "action": "复核客户计划。",
                "rationale": "基于事实和待审假设。",
                "basis_fact_ids": ["fact-1"],
            }
        ],
        "data_evidence": [
            {
                "evidence_id": "data-1",
                "purpose": "月度销售比较",
                "columns": ["sales"],
                "rows": [[1]],
            }
        ],
        "document_citations": [{"chunk_id": chunk_id, "excerpt": "客户减少采购。"}],
        "limitations": [],
    }


def test_approval_requeues_then_new_execution_publishes_draft(
    db_session, test_user
) -> None:
    company = Company(name="review-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    document = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name="review-source",
        source="test",
        status="completed",
    )
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        company_id=company.id,
        chunk_index=0,
        content="客户减少采购。",
        token_count=3,
    )
    db_session.add(chunk)
    db_session.flush()
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="华东销售为何下降",
        status="awaiting_review",
        stage="awaiting_review",
        result_data={
            "report_draft": _completed_draft(chunk_id=chunk.id),
            "answer": "待审核结论。",
        },
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(AnalysisTaskDocument(task_id=task.id, document_id=document.id))
    initial_event = create_analysis_task_event(db_session, task_id=task.id)
    initial_event.status = "worker_claimed"
    request = ReviewRequest(
        task_id=task.id,
        company_id=company.id,
        reason_code="causal_hypothesis_requires_human_review",
    )
    db_session.add(request)
    db_session.commit()

    bundle = approve_review_request(
        db_session,
        request_id=request.id,
        company_id=company.id,
        reviewer=test_user,
        note="已核验后批准。",
    )

    assert bundle is not None
    assert bundle.outbox_event_id != initial_event.id
    published_event = db_session.get(AnalysisTaskOutboxEvent, bundle.outbox_event_id)
    assert published_event is not None
    assert published_event.status == "pending"
    assert bundle.task.status == "queued"
    assert bundle.task.result_data["review_publish_only"] is True
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="review-publish", worker_id="test"
    )
    assert execution is not None
    _publish_approved_draft(db_session, execution.task, execution)

    db_session.expire_all()
    stored = db_session.get(AnalysisTask, task.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.report == FinalAnalysisReport.model_validate(
        _completed_draft(chunk_id=chunk.id)
    ).model_dump(mode="json")
    assert "report_draft" not in stored.result_data
    assert stored.result_data["review"]["status"] == "approved"
    assert stored.result_data["publication"]["decision"] == "published"


def test_approved_draft_cannot_publish_outside_frozen_chunk_scope(
    db_session, test_user
) -> None:
    company = Company(name="review-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    document_a = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name="review-source",
        source="test",
        status="completed",
    )
    document_b = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name="review-source",
        source="test",
        status="completed",
    )
    db_session.add(document_a)
    db_session.add(document_b)
    db_session.flush()
    chunk_a = DocumentChunk(
        document_id=document_a.id,
        company_id=company.id,
        chunk_index=0,
        content="客户减少采购。",
        token_count=3,
    )
    chunk_b = DocumentChunk(
        document_id=document_b.id,
        company_id=company.id,
        chunk_index=0,
        content="客户减少采购。",
        token_count=3,
    )
    db_session.add(chunk_a)
    db_session.add(chunk_b)
    db_session.flush()
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="华东销售为何下降",
        status="awaiting_review",
        stage="awaiting_review",
        result_data={
            "report_draft": _completed_draft(chunk_id=chunk_b.id),
            "answer": "待审核结论。",
        },
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(AnalysisTaskDocument(task_id=task.id, document_id=document_a.id))
    request = ReviewRequest(
        task_id=task.id,
        company_id=company.id,
        reason_code="causal_hypothesis_requires_human_review",
    )
    db_session.add(request)
    db_session.commit()

    bundle = approve_review_request(
        db_session,
        request_id=request.id,
        company_id=company.id,
        reviewer=test_user,
        note="已核验后批准。",
    )

    assert bundle is not None
    assert bundle.task.status == "queued"
    assert bundle.task.result_data["review_publish_only"] is True
    execution = claim_execution(
        db_session, task_id=task.id, celery_task_id="review-publish", worker_id="test"
    )
    assert execution is not None
    with pytest.raises(
        ReportValidationError,
        match="outside the frozen task scope",
    ):
        _publish_approved_draft(db_session, execution.task, execution)
    db_session.expire_all()
    assert execution.task.report is None
    assert "report_draft" in execution.task.result_data


def test_rejection_keeps_draft_unpublished_with_explicit_publication_state(
    db_session, test_user
) -> None:
    company = Company(name="review-rejection-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="华东销售为何下降",
        status="awaiting_review",
        stage="awaiting_review",
        result_data={"report_draft": {}, "answer": "待审核结论。"},
    )
    db_session.add(task)
    db_session.flush()
    request = ReviewRequest(
        task_id=task.id,
        company_id=company.id,
        reason_code="causal_hypothesis_requires_human_review",
    )
    db_session.add(request)
    db_session.commit()

    rejected = reject_review_request(
        db_session,
        request_id=request.id,
        company_id=company.id,
        reviewer=test_user,
        note="证据不足。",
    )

    assert rejected is not None
    assert rejected.status == "partial"
    assert rejected.report is None
    assert rejected.result_data["publication"] == {
        "decision": "not_published",
        "report_location": "report_draft",
        "reason_code": "human_review_rejected",
    }
