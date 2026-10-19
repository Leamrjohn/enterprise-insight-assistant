from datetime import datetime, timedelta, timezone

from app.modules.memory.models import AnalysisMemory
from app.modules.memory.service import (
    DEFAULT_MEMORY_TTL,
    persist_report_memory,
    planner_memories,
    select_planner_memories,
)
from app.modules.memory.sources import MemorySource
from app.modules.organizations.models import Company, CompanyMember
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.workflow.models import AnalysisTask


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
    assert memory.expires_at is not None
    assert datetime.now(timezone.utc) < memory.expires_at <= (
        datetime.now(timezone.utc) + DEFAULT_MEMORY_TTL
    )
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


def test_memory_write_gate_rejects_unpublished_or_factless_reports(
    db_session, test_user
) -> None:
    company = Company(name="memory-write-gate-company")
    db_session.add(company)
    db_session.flush()
    unpublished_task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="not published",
        status="queued",
        stage="queued",
    )
    factless_task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="factless",
        status="partial",
        stage="completed",
    )
    db_session.add_all([unpublished_task, factless_task])
    db_session.flush()

    assert (
        persist_report_memory(
            db_session, task=unpublished_task, report=_partial_report()
        )
        is None
    )
    factless_report = _partial_report().model_copy(update={"confirmed_facts": []})
    assert (
        persist_report_memory(db_session, task=factless_task, report=factless_report)
        is None
    )
    assert db_session.query(MemorySource).count() == 0
    assert db_session.query(AnalysisMemory).count() == 0


def test_expired_or_deleted_source_memory_is_never_selected(db_session, test_user) -> None:
    company = Company(name="memory-expiry-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(company_id=company.id, user_id=test_user.id, role="analyst")
    )
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="source task",
        status="completed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    source = MemorySource(
        company_id=company.id,
        source_task_id=task.id,
        source_type="validated_report",
        idempotency_key=f"source-delete:{task.id}",
    )
    db_session.add(source)
    db_session.flush()
    expired = AnalysisMemory(
        company_id=company.id,
        user_id=test_user.id,
        source_task_id=task.id,
        memory_source_id=source.id,
        memory_type="validated_report_facts",
        content={"fact": "expired"},
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    db_session.add(expired)
    db_session.commit()

    assert planner_memories(db_session, company_id=company.id, user_id=test_user.id) == []

    expired.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.commit()
    assert planner_memories(db_session, company_id=company.id, user_id=test_user.id)

    db_session.delete(source)
    db_session.commit()
    assert db_session.query(AnalysisMemory).count() == 0
    assert planner_memories(db_session, company_id=company.id, user_id=test_user.id) == []


def test_planner_memory_selection_has_a_token_budget_and_metadata_only_manifest(
    db_session, test_user
) -> None:
    company = Company(name="memory-budget-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(company_id=company.id, user_id=test_user.id, role="analyst")
    )
    small_task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="small",
        status="partial",
        stage="completed",
    )
    large_task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="large",
        status="partial",
        stage="completed",
    )
    db_session.add_all([small_task, large_task])
    db_session.flush()
    db_session.add_all(
        [
            MemorySource(
                company_id=company.id,
                source_task_id=small_task.id,
                source_type="validated_report",
                idempotency_key=f"budget:{small_task.id}",
            ),
            MemorySource(
                company_id=company.id,
                source_task_id=large_task.id,
                source_type="validated_report",
                idempotency_key=f"budget:{large_task.id}",
            ),
        ]
    )
    db_session.flush()
    sources = {
        source.source_task_id: source
        for source in db_session.query(MemorySource).filter(
            MemorySource.source_task_id.in_([small_task.id, large_task.id])
        )
    }
    db_session.add_all(
        [
            AnalysisMemory(
                company_id=company.id,
                user_id=test_user.id,
                source_task_id=small_task.id,
                memory_source_id=sources[small_task.id].id,
                memory_type="validated_report_facts",
                content={"fact": "small"},
            ),
            AnalysisMemory(
                company_id=company.id,
                user_id=test_user.id,
                source_task_id=large_task.id,
                memory_source_id=sources[large_task.id].id,
                memory_type="validated_report_facts",
                content={"fact": "x" * 4000},
            ),
        ]
    )
    db_session.commit()

    memories, manifest = select_planner_memories(
        db_session,
        company_id=company.id,
        user_id=test_user.id,
        max_tokens=100,
    )

    assert memories
    assert all("content" in memory for memory in memories)
    assert manifest["version"] == "planner-memory/v1"
    assert manifest["max_tokens"] == 100
    assert manifest["selected_tokens"] <= 100
    assert any(
        fragment["decision"] == "omitted"
        and fragment["reason"] == "token_budget_exhausted"
        for fragment in manifest["fragments"]
    )
    assert all("content" not in fragment for fragment in manifest["fragments"])
