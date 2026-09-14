from app.modules.workflow.models import AnalysisTask
from app.modules.organizations.models import Company, CompanyMember
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.observability.service import get_company_task_metrics


def test_company_task_metrics_are_scoped_and_aggregate_persisted_values(
    db_session, test_user
) -> None:
    company = Company(name="metrics-company")
    other_company = Company(name="other-metrics-company")
    db_session.add_all([company, other_company])
    db_session.flush()
    db_session.add(
        CompanyMember(
            user_id=test_user.id,
            company_id=company.id,
            role="owner",
            status="approved",
        )
    )
    tasks = [
        AnalysisTask(
            user_id=test_user.id,
            company_id=company.id,
            question="completed",
            status="completed",
            stage="completed",
            attempt_count=1,
            duration_ms=100,
            result_data={
                "knowledge_result": {"status": "succeeded"},
                "review_result": {"validation": {"citations_valid": True}},
            },
        ),
        AnalysisTask(
            user_id=test_user.id,
            company_id=company.id,
            question="partial",
            status="partial",
            stage="completed",
            attempt_count=3,
            duration_ms=300,
            result_data={
                "knowledge_result": {"status": "insufficient_evidence"},
                "review_result": {"validation": {"citations_valid": False}},
            },
        ),
        AnalysisTask(
            user_id=test_user.id,
            company_id=other_company.id,
            question="other tenant",
            status="failed",
            stage="completed",
            attempt_count=9,
            duration_ms=999,
        ),
    ]
    db_session.add_all(tasks)
    db_session.flush()
    db_session.add(
        ModelCallRecord(
            task_id=tasks[0].id,
            node_name="planner",
            provider="test",
            model_name="test-model",
            prompt_tokens=11,
            completion_tokens=7,
            cost=0.01,
            duration_ms=10,
            result_category="success",
        )
    )
    db_session.commit()

    metrics = get_company_task_metrics(db_session, company_id=company.id)

    assert metrics.total_tasks == 2
    assert metrics.terminal_tasks == 2
    assert metrics.completed_tasks == 1
    assert metrics.partial_tasks == 1
    assert metrics.failed_tasks == 0
    assert metrics.completion_rate == 0.5
    assert metrics.partial_rate == 0.5
    assert metrics.retry_count == 2
    assert metrics.duration_p50_ms == 100
    assert metrics.duration_p95_ms == 300
    assert metrics.model_calls == 1
    assert metrics.model_tokens == 18
    assert metrics.model_cost == "0.010000"
    assert metrics.rag_sufficient_rate == 0.5
    assert metrics.citation_failure_rate == 0.5
