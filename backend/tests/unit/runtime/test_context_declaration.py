"""C2 step 2: call sites declare their prompt sections; the ledger stores counts."""

from types import SimpleNamespace

from app.core.tokenizer import count_tokens
from app.modules.runtime.context_measurement import (
    context_usage,
    declare_sections,
    take_declared_sections,
)
from app.modules.runtime.model_governance import (
    model_call_scope,
    record_model_call,
    reserve_model_call,
)
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask

QUESTION = "华东区2025年8月销售额是多少？"


# --- declare / take ----------------------------------------------------------


def test_a_declaration_is_taken_once():
    declare_sections(system="系统提示", question=QUESTION)

    assert take_declared_sections() == {"system": "系统提示", "question": QUESTION}
    assert take_declared_sections() is None  # a retry must not reuse it


def test_nothing_declared_gives_none():
    take_declared_sections()  # clear anything left by another test

    assert take_declared_sections() is None


# --- context_usage ------------------------------------------------------------


def test_declared_sections_become_counts():
    usage = context_usage({"system": "系统提示", "question": QUESTION})

    assert usage == {
        "declared": True,
        "tokens": {
            "system": count_tokens("系统提示"),
            "question": count_tokens(QUESTION),
            "total": count_tokens("系统提示") + count_tokens(QUESTION),
        },
    }


def test_undeclared_call_is_marked_not_dropped():
    assert context_usage(None) == {"declared": False}


def test_usage_never_contains_section_text():
    usage = context_usage({"question": QUESTION})

    assert "华东" not in str(usage)


# --- end to end through the ledger --------------------------------------------


def _task(test_user) -> AnalysisTask:
    return AnalysisTask(
        user_id=test_user.id,
        question="c2 ledger",
        status="queued",
        stage="queued",
        model_budget_snapshot={
            "max_calls": 3,
            "max_calls_per_node": 3,
            "max_repairs": 1,
            "max_total_tokens": 1000,
            "max_cost": "1.00",
        },
        model_budget_usage={
            "calls": 0,
            "tokens": 0,
            "cost": "0.00",
            "reserved_cost": "0.00",
            "unknown_cost_calls": 0,
            "repairs": 0,
            "calls_by_node": {},
        },
    )


def test_ledger_keeps_section_counts_after_settlement(db_session, test_user):
    task = _task(test_user)
    db_session.add(task)
    db_session.commit()

    with model_call_scope(
        db_session, task=task, attempt=SimpleNamespace(id=None), node_name="planner"
    ):
        declare_sections(system="系统提示", question=QUESTION)
        scope = reserve_model_call(
            provider="local", model_name="test-model", estimated_prompt_tokens=20
        )
        assert scope is not None
        record_model_call(
            scope,
            provider="local",
            model_name="test-model",
            prompt_tokens=20,
            completion_tokens=5,
            duration_ms=1,
            result_category="success",
            resource_usage={"finish_reason": "stop"},
        )
        second = reserve_model_call(provider="local", model_name="test-model")
        assert second is not None

    first, retry = (
        db_session.query(ModelCallRecord)
        .filter(ModelCallRecord.task_id == task.id)
        .order_by(ModelCallRecord.id)
        .all()
    )
    assert first.resource_usage["context_tokens"]["declared"] is True
    assert first.resource_usage["context_tokens"]["tokens"]["question"] == count_tokens(
        QUESTION
    )
    assert first.resource_usage["finish_reason"] == "stop"  # merged, not replaced
    assert retry.resource_usage["context_tokens"] == {"declared": False}
    assert "华东" not in str(first.resource_usage)


def test_undeclared_call_keeps_the_gateway_split(db_session, test_user):
    task = _task(test_user)
    db_session.add(task)
    db_session.commit()

    with model_call_scope(
        db_session, task=task, attempt=SimpleNamespace(id=None), node_name="reviewer"
    ):
        take_declared_sections()  # nothing left over from another test
        reserve_model_call(
            provider="local",
            model_name="test-model",
            request_parts={"prompt": QUESTION, "system_prompt": "系统提示"},
        )

    record = db_session.query(ModelCallRecord).filter_by(task_id=task.id).one()
    usage = record.resource_usage["context_tokens"]
    assert usage["declared"] == "auto"
    assert usage["tokens"]["prompt"] == count_tokens(QUESTION)
    assert "华东" not in str(record.resource_usage)
