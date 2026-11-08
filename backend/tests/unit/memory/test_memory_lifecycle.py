"""Selection, conflicts, flag and review, cleanup, and the review API."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app.db.session import get_db, set_tenant_scope
from app.main import app
from app.modules.identity.authentication import get_current_user
from app.modules.identity.models import User
from app.modules.memory.models import AnalysisMemory, MemoryAuditEvent
from app.modules.memory.service import (
    MemoryReview,
    MemoryTransitionError,
    cleanup_memories,
    flag_memories_from_model,
    flag_memory,
    memory_relevance,
    persist_report_memory,
    review_memory,
    select_planner_memories,
)
from app.modules.memory.sources import MemorySource
from app.modules.organizations.models import Company, CompanyMember
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.workflow.models import AnalysisTask
from fastapi.testclient import TestClient


def _member(db, company, name, role="owner") -> User:
    user = User(name=name, api_key=f"{name}-key")
    db.add(user)
    db.flush()
    db.add(
        CompanyMember(
            user_id=user.id, company_id=company.id, role=role, status="approved"
        )
    )
    db.flush()
    return user


def _memory(db, company, user, statement, **fields) -> AnalysisMemory:
    set_tenant_scope(db, company.id)
    task = AnalysisTask(
        user_id=user.id,
        company_id=company.id,
        question="q",
        status="completed",
        stage="completed",
    )
    db.add(task)
    db.flush()
    source = MemorySource(
        company_id=company.id,
        source_task_id=task.id,
        source_type="validated_report",
        idempotency_key=f"lifecycle:{task.id}",
    )
    db.add(source)
    db.flush()
    memory = AnalysisMemory(
        company_id=company.id,
        user_id=user.id,
        source_task_id=task.id,
        memory_source_id=source.id,
        memory_type="validated_report_facts",
        content={"confirmed_facts": [{"statement": statement}]},
        expires_at=fields.pop(
            "expires_at", datetime.now(timezone.utc) + timedelta(days=30)
        ),
        **fields,
    )
    db.add(memory)
    db.flush()
    return memory


@pytest.fixture
def world(db_session):
    company = Company(name="memory-lifecycle")
    other = Company(name="memory-lifecycle-other")
    db_session.add_all([company, other])
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    owner = _member(db_session, company, "memory-owner")
    return SimpleNamespace(
        db=db_session,
        company=company,
        other=other,
        owner=owner,
        add=lambda text, **f: _memory(db_session, company, owner, text, **f),
    )


def _selected(world, question=None, **kwargs) -> list[int]:
    payloads, _ = select_planner_memories(
        world.db,
        company_id=world.company.id,
        user_id=world.owner.id,
        question=question,
        **kwargs,
    )
    return [p["memory_id"] for p in payloads]


def test_relevance_rewards_identifying_numbers_over_common_words():
    text = "客户CUST-0280已纳入重点催收"
    assert memory_relevance("CUST-0280回款风险", text) > 0.3
    assert memory_relevance("CUST-0001回款风险", text) < 0.3
    assert memory_relevance("你好", text) == 0.0


def test_only_relevant_memories_are_selected(world):
    relevant = world.add("客户CUST-0280已纳入重点催收")
    world.add("2025年9月物流仓储费用环比持平")
    assert _selected(world, "CUST-0280的回款风险？") == [relevant.id]
    assert _selected(world, "你好") == []


def test_older_relevant_memory_beats_newer_irrelevant_ones(world):
    old = world.add(
        "客户CUST-0280已纳入重点催收",
        created_at=datetime.now(timezone.utc) - timedelta(days=25),
    )
    for index in range(10):
        world.add(f"2025年9月费用第{index}项持平")
    assert old.id in _selected(world, "CUST-0280的回款风险？")


def test_more_important_memory_ranks_first(world):
    low = world.add("CUST-0280回款风险低", importance=0.2)
    high = world.add("CUST-0280回款风险高", importance=0.9)
    assert _selected(world, "CUST-0280回款风险")[:2] == [high.id, low.id]


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "flagged"},
        {"status": "superseded"},
        {"status": "revoked"},
        {"status": "deleted"},
        {"revoked": True},
        {"business_valid_until": date(2020, 1, 1)},
        {"expires_at": datetime(2020, 1, 1, tzinfo=timezone.utc)},
    ],
)
def test_hard_filters_hold_whatever_the_relevance(world, fields):
    world.add("CUST-0280回款风险", **fields)
    assert _selected(world, "CUST-0280回款风险") == []


def test_other_company_and_colleague_memories_are_never_selected(world):
    colleague = _member(world.db, world.company, "memory-colleague", role="analyst")
    _memory(world.db, world.company, colleague, "CUST-0280回款风险")
    outsider = _member(world.db, world.other, "memory-outsider")
    _memory(world.db, world.other, outsider, "CUST-0280回款风险")
    set_tenant_scope(world.db, world.company.id)
    assert _selected(world, "CUST-0280回款风险") == []


def test_use_is_recorded_only_when_asked_and_only_for_selected(world):
    used = world.add("CUST-0280回款风险")
    other = world.add("费用持平")
    _selected(world, "CUST-0280回款风险")
    assert used.use_count == 0
    _selected(world, "CUST-0280回款风险", record_use=True)
    assert used.use_count == 1 and used.last_used_at is not None
    assert other.use_count == 0


def _report(statement: str) -> FinalAnalysisReport:
    return FinalAnalysisReport.model_validate(
        {
            "status": "completed",
            "executive_summary": "s",
            "confirmed_facts": [
                {"fact_id": "f1", "statement": statement, "data_evidence_ids": ["e1"]}
            ],
            "data_evidence": [
                {
                    "evidence_id": "e1",
                    "purpose": "p",
                    "sql": "SELECT 1",
                    "columns": ["x"],
                    "rows": [[1]],
                }
            ],
        }
    )


def _task(world, question) -> AnalysisTask:
    task = AnalysisTask(
        user_id=world.owner.id,
        company_id=world.company.id,
        question=question,
        status="completed",
        stage="completed",
    )
    world.db.add(task)
    world.db.flush()
    return task


def _actions(world, memory_id) -> list[str]:
    return [
        event.action
        for event in world.db.query(MemoryAuditEvent)
        .filter(MemoryAuditEvent.original_memory_id == memory_id)
        .order_by(MemoryAuditEvent.id)
    ]


def test_newer_report_on_the_same_question_replaces_the_old_value(world):
    question = "CUST-0280的未收余额是多少？"
    old = persist_report_memory(
        world.db, task=_task(world, question), report=_report("CUST-0280未收余额100元")
    )
    world.db.flush()
    new = persist_report_memory(
        world.db, task=_task(world, question), report=_report("CUST-0280未收余额200元")
    )
    world.db.flush()
    assert old.status == "superseded" and old.superseded_by_id == new.id
    assert _selected(world, question) == [new.id]
    assert _actions(world, old.id) == ["created", "superseded"]


def test_same_facts_again_extend_retention_without_a_new_memory(world):
    question = "CUST-0280的未收余额是多少？"
    first = persist_report_memory(
        world.db, task=_task(world, question), report=_report("CUST-0280未收余额100元")
    )
    world.db.flush()
    first.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    again = persist_report_memory(
        world.db, task=_task(world, question), report=_report("CUST-0280未收余额100元")
    )
    assert again.id == first.id
    assert first.expires_at > datetime.now(timezone.utc) + timedelta(days=20)
    assert _actions(world, first.id) == ["created", "duplicate_ignored"]


def test_flagged_memory_stops_being_used_before_any_review(world):
    memory = world.add("CUST-0280回款风险")
    flag_memory(world.db, memory, actor_kind="user", reason="数字不对")
    world.db.flush()
    assert _selected(world, "CUST-0280回款风险") == []
    assert _actions(world, memory.id) == ["flagged"]


def test_only_an_active_memory_can_be_flagged(world):
    memory = world.add("x", status="revoked")
    with pytest.raises(MemoryTransitionError):
        flag_memory(world.db, memory, actor_kind="user", reason="r")


def _review(memory, world, decision, **fields):
    review_memory(
        world.db,
        memory,
        MemoryReview(
            decision=decision,
            reason="审核",
            reviewer_user_id=world.owner.id,
            **fields,
        ),
    )
    world.db.flush()


def test_restore_puts_a_flagged_memory_back_in_use(world):
    memory = world.add("CUST-0280回款风险", status="flagged")
    _review(memory, world, "restore")
    assert _selected(world, "CUST-0280回款风险") == [memory.id]
    assert _actions(world, memory.id) == ["review_restore"]


def test_revoke_keeps_it_out_for_good(world):
    memory = world.add("CUST-0280回款风险", status="flagged")
    _review(memory, world, "revoke")
    assert memory.revoked is True
    assert _selected(world, "CUST-0280回款风险") == []


def test_replace_points_at_another_active_memory(world):
    wrong = world.add("CUST-0280回款风险100", status="flagged")
    right = world.add("CUST-0280回款风险200")
    _review(wrong, world, "replace", replacement_memory_id=right.id)
    assert wrong.status == "superseded" and wrong.superseded_by_id == right.id
    assert _selected(world, "CUST-0280回款风险") == [right.id]


@pytest.mark.parametrize("target", ["missing", "itself", "inactive", "other_company"])
def test_replacement_must_be_a_valid_active_memory(world, target):
    wrong = world.add("x", status="flagged")
    outsider = _member(world.db, world.other, "replace-outsider")
    candidates = {
        "missing": 999_999_999,
        "itself": wrong.id,
        "inactive": world.add("y", status="revoked").id,
        "other_company": _memory(world.db, world.other, outsider, "z").id,
    }
    set_tenant_scope(world.db, world.company.id)
    with pytest.raises(MemoryTransitionError):
        _review(wrong, world, "replace", replacement_memory_id=candidates[target])
    assert wrong.status == "flagged"


def test_only_a_flagged_memory_can_be_reviewed(world):
    with pytest.raises(MemoryTransitionError):
        _review(world.add("x"), world, "revoke")


def test_model_can_only_flag_memories_this_task_used(world):
    used = world.add("a")
    unrelated = world.add("b")
    flagged = flag_memories_from_model(
        world.db,
        company_id=world.company.id,
        flags=[
            {"memory_id": used.id, "reason": "矛盾"},
            {"memory_id": unrelated.id, "reason": "越权"},
            {"memory_id": 999_999_999, "reason": "不存在"},
        ],
        allowed_ids={used.id},
    )
    assert flagged == [used.id]
    assert used.status == "flagged" and unrelated.status == "active"
    event = (
        world.db.query(MemoryAuditEvent)
        .filter(MemoryAuditEvent.original_memory_id == used.id)
        .one()
    )
    assert event.actor_kind == "model"


NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=10)
PAST = NOW - timedelta(days=1)


def test_cleanup_soft_deletes_what_has_expired(world):
    expired = world.add("expired", expires_at=PAST)
    invalid = world.add(
        "invalid", expires_at=FUTURE, business_valid_until=date(2026, 1, 1)
    )
    fresh = world.add("fresh", expires_at=FUTURE)
    result = cleanup_memories(world.db, company_id=world.company.id, now=NOW)
    assert result == {"soft_deleted": 2, "purged": 0}
    assert expired.status == invalid.status == "deleted"
    assert expired.deleted_at == NOW
    assert fresh.status == "active"
    assert _actions(world, expired.id) == ["soft_deleted"]


def test_superseded_memory_waits_for_its_retention(world):
    memory = world.add("old", status="superseded", expires_at=FUTURE)
    cleanup_memories(world.db, company_id=world.company.id, now=NOW)
    assert memory.status == "superseded"


def test_flagged_memory_waits_for_review_even_if_expired(world):
    memory = world.add("flagged", status="flagged", expires_at=PAST)
    cleanup_memories(world.db, company_id=world.company.id, now=NOW)
    assert memory.status == "flagged"


def test_purge_happens_only_after_ninety_days_and_the_audit_survives(world):
    recent = world.add(
        "recent", status="deleted", deleted_at=NOW - timedelta(days=89), expires_at=PAST
    )
    old = world.add(
        "old", status="deleted", deleted_at=NOW - timedelta(days=91), expires_at=PAST
    )
    old_id = old.id
    result = cleanup_memories(world.db, company_id=world.company.id, now=NOW)
    assert result["purged"] == 1
    world.db.expire_all()
    assert world.db.get(AnalysisMemory, old_id) is None
    assert world.db.get(AnalysisMemory, recent.id) is not None
    trail = (
        world.db.query(MemoryAuditEvent)
        .filter(MemoryAuditEvent.original_memory_id == old_id)
        .all()
    )
    assert [event.action for event in trail] == ["purged"]
    assert trail[0].memory_id is None


def test_cleanup_only_touches_its_own_company(world):
    outsider = _member(world.db, world.other, "cleanup-outsider")
    theirs = _memory(world.db, world.other, outsider, "x", expires_at=PAST)
    set_tenant_scope(world.db, world.company.id)
    cleanup_memories(world.db, company_id=world.company.id, now=NOW)
    assert theirs.status == "active"


@pytest.fixture
def api(world):
    def client_for(user: User) -> TestClient:
        def override_db():
            yield world.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield client_for
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_api_flag_then_review_by_an_admin(world, api):
    memory = world.add("CUST-0280回款风险")
    client = api(world.owner)
    assert (
        client.post(f"/memories/{memory.id}/flag", json={"reason": "错"}).json()[
            "status"
        ]
        == "flagged"
    )
    listed = client.get("/memories", params={"status": "flagged"}).json()
    assert [item["id"] for item in listed] == [memory.id]
    reviewed = client.post(
        f"/memories/{memory.id}/review",
        json={"decision": "revoke", "reason": "确认错误"},
    )
    assert reviewed.json()["status"] == "revoked"
    audit = client.get(f"/memories/{memory.id}/audit").json()
    assert [event["action"] for event in audit] == ["flagged", "review_revoke"]


def test_api_review_needs_an_admin(world, api):
    analyst = _member(world.db, world.company, "memory-analyst", role="analyst")
    memory = _memory(world.db, world.company, analyst, "x", status="flagged")
    response = api(analyst).post(
        f"/memories/{memory.id}/review", json={"decision": "restore", "reason": "r"}
    )
    assert response.status_code == 403
    assert memory.status == "flagged"


def test_api_analyst_can_flag_only_their_own_memory(world, api):
    analyst = _member(world.db, world.company, "memory-analyst-2", role="analyst")
    theirs = world.add("owner's memory")
    mine = _memory(world.db, world.company, analyst, "mine")
    client = api(analyst)
    assert (
        client.post(f"/memories/{theirs.id}/flag", json={"reason": "r"}).status_code
        == 404
    )
    assert (
        client.post(f"/memories/{mine.id}/flag", json={"reason": "r"}).status_code
        == 200
    )
    assert [m["id"] for m in client.get("/memories").json()] == [mine.id]


def test_api_cannot_reach_another_companys_memory(world, api):
    outsider = _member(world.db, world.other, "api-outsider")
    theirs = _memory(world.db, world.other, outsider, "x")
    set_tenant_scope(world.db, world.company.id)
    client = api(world.owner)
    assert (
        client.post(f"/memories/{theirs.id}/flag", json={"reason": "r"}).status_code
        == 404
    )
    assert client.get(f"/memories/{theirs.id}/audit").status_code == 404
    assert theirs.status == "active"


def test_api_invalid_transition_is_a_conflict(world, api):
    memory = world.add("x")
    response = api(world.owner).post(
        f"/memories/{memory.id}/review", json={"decision": "restore", "reason": "r"}
    )
    assert response.status_code == 409


def test_api_cannot_write_memory_content(world, api):
    memory = world.add("x", status="flagged")
    response = api(world.owner).post(
        f"/memories/{memory.id}/review",
        json={
            "decision": "restore",
            "reason": "r",
            "content": {"confirmed_facts": [{"statement": "伪造"}]},
        },
    )
    assert response.status_code == 200
    assert memory.content == {"confirmed_facts": [{"statement": "x"}]}
