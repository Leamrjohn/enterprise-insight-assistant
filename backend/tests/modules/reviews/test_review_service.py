from app.modules.workflow.models import AnalysisTask
from app.modules.organizations.models import Company
from app.modules.reviews.models import ReviewRequest
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.reviews.service import approve_review_request
from app.modules.workflow.execution import claim_execution
from app.modules.workflow.tasks import _publish_approved_draft


def _completed_draft() -> dict:
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
                "citation_chunk_ids": [1],
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
        "document_citations": [{"chunk_id": 1, "excerpt": "客户减少采购。"}],
        "limitations": [],
    }


def test_approval_requeues_then_new_execution_publishes_draft(
    db_session, test_user
) -> None:
    company = Company(name="review-company")
    db_session.add(company)
    db_session.flush()
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="华东销售为何下降",
        status="awaiting_review",
        stage="awaiting_review",
        result_data={"report_draft": _completed_draft(), "answer": "待审核结论。"},
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
    _publish_approved_draft(db_session, execution.task, execution)

    db_session.expire_all()
    stored = db_session.get(AnalysisTask, task.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.report == FinalAnalysisReport.model_validate(
        _completed_draft()
    ).model_dump(mode="json")
    assert "report_draft" not in stored.result_data
    assert stored.result_data["review"]["status"] == "approved"
