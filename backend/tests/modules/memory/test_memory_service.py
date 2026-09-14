from app.modules.workflow.models import AnalysisTask
from app.modules.organizations.models import Company, CompanyMember
from app.modules.memory.sources import MemorySource
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.memory.service import persist_report_memory, planner_memories


def _partial_report() -> FinalAnalysisReport:
    return FinalAnalysisReport.model_validate(
        {
            "status": "partial",
            "executive_summary": "只确认了销售下降事实。",
            "confirmed_facts": [
                {
                    "fact_id": "fact-1",
                    "statement": "华东销售额下降。",
                    "data_evidence_ids": ["data-1"],
                }
            ],
            "hypotheses": [],
            "recommendations": [],
            "data_evidence": [
                {
                    "evidence_id": "data-1",
                    "purpose": "月度销售比较",
                    "columns": ["sales"],
                    "rows": [[100]],
                }
            ],
            "document_citations": [],
            "limitations": [
                {
                    "code": "insufficient_documents",
                    "message": "资料不足。",
                    "next_step": "补充资料。",
                }
            ],
        }
    )


def test_planner_memory_is_scoped_to_active_company_membership(
    db_session, test_user
) -> None:
    company = Company(name="memory-company")
    db_session.add(company)
    db_session.flush()
    membership = CompanyMember(
        company_id=company.id, user_id=test_user.id, role="analyst"
    )
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="销售分析",
        status="partial",
        stage="completed",
    )
    db_session.add_all([membership, task])
    db_session.flush()

    memory = persist_report_memory(db_session, task=task, report=_partial_report())
    db_session.commit()

    assert memory is not None
    assert memory.source is not None
    assert memory.source.idempotency_key == f"validated-report:{task.id}"
    assert db_session.query(MemorySource).count() == 1
    assert (
        persist_report_memory(db_session, task=task, report=_partial_report()).id
        == memory.id
    )
    visible = planner_memories(db_session, company_id=company.id, user_id=test_user.id)
    assert visible[0]["content"]["confirmed_facts"][0]["fact_id"] == "fact-1"
    assert "hypotheses" not in visible[0]["content"]

    membership.status = "rejected"
    db_session.commit()
    assert (
        planner_memories(db_session, company_id=company.id, user_id=test_user.id) == []
    )
