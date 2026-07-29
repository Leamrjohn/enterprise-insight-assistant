from app.models.analysis_task import AnalysisTask
from app.models.company import Company
from app.models.tool_call_record import ToolCallRecord
from app.services.workflow_evaluation import evaluate_company_workflows


def test_workflow_evaluation_uses_persisted_terminal_runs_and_tool_audit(
    db_session, test_user
) -> None:
    company = Company(name="workflow-evaluation-company")
    db_session.add(company)
    db_session.flush()
    tasks = [
        AnalysisTask(
            user_id=test_user.id,
            company_id=company.id,
            question="a",
            status="completed",
            stage="completed",
            duration_ms=100,
        ),
        AnalysisTask(
            user_id=test_user.id,
            company_id=company.id,
            question="b",
            status="partial",
            stage="completed",
            duration_ms=300,
        ),
    ]
    db_session.add_all(tasks)
    db_session.flush()
    db_session.add_all(
        [
            ToolCallRecord(
                task_id=tasks[0].id,
                tool_name="rag_search",
                status="succeeded",
                metadata_json={},
            ),
            ToolCallRecord(
                task_id=tasks[1].id,
                tool_name="rag_search",
                status="denied",
                metadata_json={},
            ),
        ]
    )
    db_session.commit()

    result = evaluate_company_workflows(db_session, company_id=company.id)

    assert result.total_terminal_runs == 2
    assert result.completion_rate == 0.5
    assert result.duration_p95_ms == 300
    assert result.tool_denial_rate == 0.5
