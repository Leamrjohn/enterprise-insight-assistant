"""Which period a question asks about, and retrieval honouring document validity."""

import json
from datetime import date
from pathlib import Path

import pytest
from app.db.session import set_tenant_scope
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.documents.versioning import register_document_version
from app.modules.identity.models import User
from app.modules.knowledge.agent import KnowledgeAgent
from app.modules.knowledge.rag.engine import EvidenceRef, build_prompt
from app.modules.knowledge.rag.retrieval import retrieve_evidence
from app.modules.knowledge.rag.validity import (
    ValidityWindow,
    resolve_validity_window,
)
from app.modules.knowledge.tool import RAGTool
from app.modules.organizations.models import Company

TODAY = date(2026, 11, 2)
TRAPS = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "evaluation_retrieval"
    / "version_traps_v1.json"
)


@pytest.mark.parametrize(
    ("question", "start", "end"),
    [
        ("出差住宿费每晚报销上限是多少？", TODAY, TODAY),
        ("现在出差住宿费上限是多少？", TODAY, TODAY),
        ("2024年6月时报销上限是多少？", date(2024, 6, 1), date(2024, 6, 30)),
        ("2024-06-15 的规定是什么", date(2024, 6, 15), date(2024, 6, 15)),
        ("2024年6月15日的规定是什么", date(2024, 6, 15), date(2024, 6, 15)),
        ("2024年十月时折扣上限", date(2024, 10, 1), date(2024, 10, 31)),
        ("2025年Q2的规定", date(2025, 4, 1), date(2025, 6, 30)),
        ("2025年第三季度的规定", date(2025, 7, 1), date(2025, 9, 30)),
        ("2025年上半年的规定", date(2025, 1, 1), date(2025, 6, 30)),
        ("2024年的规定", date(2024, 1, 1), date(2024, 12, 31)),
        ("2023版差旅标准是多少", date(2023, 1, 1), date(2023, 12, 31)),
        ("去年的规定", date(2025, 1, 1), date(2025, 12, 31)),
        ("2024年和2025年的规定有什么不同", date(2024, 1, 1), date(2025, 12, 31)),
        ("2024年的规定和现在有什么不同", date(2024, 1, 1), TODAY),
        ("旧版差旅标准是什么", date.min, TODAY),
        ("2024年13月的规定", TODAY, TODAY),
    ],
)
def test_window_from_question(question, start, end):
    assert resolve_validity_window(question, TODAY) == ValidityWindow(start, end)


def test_window_covers_every_labelled_trap_date():
    for case in json.loads(TRAPS.read_text(encoding="utf-8"))["cases"]:
        window = resolve_validity_window(case["question"], TODAY)
        if case["kind"] == "current":
            assert window == ValidityWindow(TODAY, TODAY), case["case_id"]
        else:
            as_of = date.fromisoformat(case["as_of"])
            assert window.start <= as_of <= window.end, case["case_id"]


@pytest.mark.parametrize(
    "value",
    [["2025-01-01"], "2025-01-01", ["2025-02-01", "2025-01-01"], ["x", "y"], [1, 2]],
)
def test_malformed_window_parameter_is_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        ValidityWindow.from_parameter(value)


class _FixedEmbedder:
    def embed(self, _question: str) -> list[float]:
        return [1.0, *([0.0] * 383)]


def _document(db, *, company, user, name) -> Documents:
    document = Documents(
        uploaded_by_user_id=user.id,
        company_id=company.id,
        name=name,
        content=name,
        source="test",
        status="completed",
    )
    db.add(document)
    db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            company_id=company.id,
            chunk_strategy="paragraph_v1",
            chunk_index=0,
            content=name,
            token_count=1,
            embedding=[1.0, *([0.0] * 383)],
        )
    )
    db.flush()
    return document


@pytest.fixture
def versions(db_session):
    user = User(name="validity-user", api_key="validity-key")
    company = Company(name="validity-company")
    db_session.add_all([user, company])
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    old = _document(db_session, company=company, user=user, name="v1")
    new = _document(db_session, company=company, user=user, name="v2")
    unknown = _document(db_session, company=company, user=user, name="unregistered")
    register_document_version(
        db_session,
        document=old,
        version_group="travel",
        version_number=1,
        effective_from=date(2023, 1, 1),
    )
    register_document_version(
        db_session,
        document=new,
        version_group="travel",
        version_number=2,
        effective_from=date(2025, 1, 1),
    )
    return db_session, company, old, new, unknown


def _retrieved_names(db, company, window):
    return {
        evidence.document_name
        for evidence in retrieve_evidence(
            db,
            "差旅",
            company.id,
            _FixedEmbedder(),
            min_score=-1.0,
            validity=window,
        )
    }


def test_new_version_retires_the_old_one(versions):
    _, _, old, new, _ = versions
    assert old.effective_to == date(2024, 12, 31)
    assert old.superseded_by_document_id == new.id
    assert new.effective_to is None and new.superseded_by_document_id is None


def test_old_version_registered_late_is_retired_at_once(db_session):
    user = User(name="late-user", api_key="late-key")
    company = Company(name="late-company")
    db_session.add_all([user, company])
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    new = _document(db_session, company=company, user=user, name="new")
    old = _document(db_session, company=company, user=user, name="old")
    for document, number, start in (
        (new, 2, date(2025, 1, 1)),
        (old, 1, date(2023, 1, 1)),
    ):
        register_document_version(
            db_session,
            document=document,
            version_group="g",
            version_number=number,
            effective_from=start,
        )
    assert old.effective_to == date(2024, 12, 31)
    assert old.superseded_by_document_id == new.id


def test_version_dates_must_follow_version_order(versions):
    db, _, _, _, unknown = versions
    with pytest.raises(ValueError, match="version order"):
        register_document_version(
            db,
            document=unknown,
            version_group="travel",
            version_number=3,
            effective_from=date(2024, 1, 1),
        )
    with pytest.raises(ValueError, match="already registered"):
        register_document_version(
            db,
            document=unknown,
            version_group="travel",
            version_number=2,
            effective_from=date(2026, 1, 1),
        )


def test_current_question_never_receives_the_retired_version(versions):
    db, company, *_ = versions
    names = _retrieved_names(db, company, ValidityWindow(TODAY, TODAY))
    assert names == {"v2", "unregistered"}


def test_historical_question_receives_the_version_valid_then(versions):
    db, company, *_ = versions
    day = date(2024, 6, 1)
    names = _retrieved_names(db, company, ValidityWindow(day, day))
    assert names == {"v1", "unregistered"}


def test_window_across_the_change_receives_both_versions(versions):
    db, company, *_ = versions
    names = _retrieved_names(
        db, company, ValidityWindow(date(2024, 1, 1), date(2025, 12, 31))
    )
    assert names == {"v1", "v2", "unregistered"}


def test_future_version_is_not_valid_today(versions):
    db, company, _, _, unknown = versions
    register_document_version(
        db,
        document=unknown,
        version_group="travel",
        version_number=3,
        effective_from=date(2027, 1, 1),
    )
    names = _retrieved_names(db, company, ValidityWindow(TODAY, TODAY))
    assert names == {"v2"}


def test_agent_takes_the_window_from_the_question_not_the_facts():
    seen: list[dict] = []

    class _Recorder(Tool):
        @property
        def name(self) -> str:
            return "rag_search"

        @property
        def description(self) -> str:
            return "records its input"

        def execute(self, input: ToolInput) -> ToolOutput:
            seen.append(input.parameters)
            return ToolOutput(
                success=True,
                data={
                    "status": "insufficient_evidence",
                    "answer": "无法回答：资料不足",
                    "evidences": [],
                },
            )

    KnowledgeAgent(rag_tool=_Recorder()).run(
        AgentInput(
            question="2024年6月时报销上限是多少？",
            user_id=1,
            context={
                "company_id": 1,
                "confirmed_facts": [
                    {"fact_id": "f", "statement": "2025年3月的营收为100元"}
                ],
            },
        )
    )
    assert seen[0]["validity_window"] == ["2024-06-01", "2024-06-30"]
    assert "2025年3月" in seen[0]["question"]


def test_tool_rejects_a_malformed_window_before_touching_the_database():
    result = RAGTool().execute(
        ToolInput(
            parameters={
                "question": "q",
                "company_id": 1,
                "validity_window": ["2025-02-01", "2025-01-01"],
            }
        )
    )
    assert not result.success
    assert result.error_code == "rag_validity_window_invalid"


def test_prompt_shows_validity_only_when_registered():
    plain = EvidenceRef(chunk_id=1, document_id=1, content="a")
    dated = EvidenceRef(
        chunk_id=2,
        document_id=2,
        content="b",
        effective_from="2025-01-01",
        applies_to="华东区域",
    )
    _, prompt, _ = build_prompt("q", [plain, dated])
    first, second = prompt.split("</evidence>")[:2]
    assert "valid_from" not in first
    assert 'valid_from="2025-01-01" valid_to="至今"' in second
    assert 'applies_to="华东区域"' in second
