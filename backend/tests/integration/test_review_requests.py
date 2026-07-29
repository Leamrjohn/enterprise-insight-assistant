from app.models.analysis_task import AnalysisTask
from app.models.review_request import ReviewRequest


def _reviewable_report() -> dict:
    return {
        "status": "completed",
        "executive_summary": "华东销售下降，需要核验客户流失假设。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "华东销售额同比下降 12%。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "重点客户流失可能是原因之一。",
                "related_fact_ids": ["fact-1"],
                "citation_chunk_ids": [101],
                "support_level": "medium",
            }
        ],
        "recommendations": [
            {
                "recommendation_id": "recommendation-1",
                "priority": "high",
                "action": "复核重点客户续约情况。",
                "rationale": "验证客户流失假设。",
                "basis_hypothesis_ids": ["hypothesis-1"],
            }
        ],
        "data_evidence": [
            {
                "evidence_id": "data-1",
                "purpose": "比较华东销售同比变化",
                "columns": ["region", "change_rate"],
                "rows": [["华东", -0.12]],
            }
        ],
        "document_citations": [
            {
                "chunk_id": 101,
                "document_id": 9,
                "excerpt": "重点客户续约率下降。",
                "score": 0.88,
            }
        ],
        "limitations": [],
    }


def test_admin_can_list_only_current_company_pending_review_requests(
    client, db_session, test_user
) -> None:
    company = client.post("/companies", json={"name": "审核公司"})
    assert company.status_code == 201

    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.json()["id"],
        question="华东销售为何下降",
        status="awaiting_review",
        stage="awaiting_review",
        result_data={"report_draft": _reviewable_report()},
    )
    db_session.add(task)
    db_session.flush()
    request = ReviewRequest(
        task_id=task.id,
        company_id=company.json()["id"],
        reason_code="causal_hypothesis_requires_human_review",
    )
    db_session.add(request)
    db_session.commit()

    response = client.get("/review-requests")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == request.id
    assert payload[0]["task_id"] == task.id
    assert payload[0]["task_question"] == "华东销售为何下降"
    assert payload[0]["status"] == "pending"
    assert payload[0]["reason_code"] == "causal_hypothesis_requires_human_review"
    assert payload[0]["report_draft"]["schema_version"] == "1.0"
    assert payload[0]["report_draft"]["confirmed_facts"][0]["fact_id"] == "fact-1"
    assert payload[0]["report_draft"]["document_citations"][0]["chunk_id"] == 101
    assert payload[0]["draft_error"] is None
    assert payload[0]["created_at"]


def test_review_queue_marks_missing_draft_as_not_approvable(
    client, db_session, test_user
) -> None:
    company = client.post("/companies", json={"name": "缺失草稿公司"})
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.json()["id"],
        question="为什么需要人工审核",
        status="awaiting_review",
        stage="awaiting_review",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        ReviewRequest(
            task_id=task.id,
            company_id=company.json()["id"],
            reason_code="causal_hypothesis_requires_human_review",
        )
    )
    db_session.commit()

    response = client.get("/review-requests")

    assert response.status_code == 200
    assert response.json()[0]["report_draft"] is None
    assert response.json()[0]["draft_error"] == "missing"
