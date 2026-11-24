"""C9c: after a publish, the summary job merges what left the window."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.settings import get_settings
from app.db.clock import database_now
from app.db.session import set_tenant_scope
from app.modules.conversations.models import ConversationMessage
from app.modules.conversations.summary import empty_summary, load_summary, save_summary
from app.modules.runtime.model_governance import reserve_model_call
from app.modules.workflow import summary_tasks, tasks
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.summary_tasks import REWRITE_EVERY, run_summary
from tests.integration.conversations.test_conversation_state import _conversation

BUDGET = {
    "max_calls": 8,
    "max_calls_per_node": 8,
    "max_repairs": 0,
    "max_total_tokens": 100000,
    "max_cost": "1",
    "summary_max_calls": 1,
}


class FakeGateway:
    """Reserves like a real gateway, then answers with ``items``."""

    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.prompts: list[str] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        reserve_model_call(
            provider="deepseek",
            model_name="summary-test-model",
            estimated_prompt_tokens=1,
            reserved_completion_tokens=1,
        )
        self.prompts.append(prompt)
        return json.dumps({"summary_items": self.items}, ensure_ascii=False)


def _task(db_session, message_count: int, budget=BUDGET) -> AnalysisTask:
    conversation = _conversation(db_session, f"summary-job-{uuid4().hex[:8]}")
    for i in range(message_count):
        db_session.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"第{i + 1}条",
                status="completed",
            )
        )
    task = AnalysisTask(
        user_id=conversation.user_id,
        company_id=conversation.company_id,
        conversation_id=conversation.id,
        question="摘要",
        status="completed",
        stage="completed",
        model_budget_snapshot=budget,
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        TaskExecutionAttempt(
            task_id=task.id,
            execution_id=str(uuid4()),
            status="completed",
            lease_expires_at=database_now(db_session),
        )
    )
    db_session.flush()
    return task


def _ids(db_session, task) -> list[int]:
    messages = (
        db_session.query(ConversationMessage)
        .filter_by(conversation_id=task.conversation_id)
        .order_by(ConversationMessage.id)
    )
    return [m.id for m in messages]


def test_a_short_conversation_calls_nothing(db_session) -> None:
    task = _task(db_session, 8)
    gateway = FakeGateway([])

    assert run_summary(db_session, task.id, gateway) == "in_window"
    assert gateway.prompts == []


def test_the_messages_that_left_the_window_are_summarized_and_charged(
    db_session,
) -> None:
    task = _task(db_session, 12)
    ids = _ids(db_session, task)
    first = ids[0]
    gateway = FakeGateway(
        [
            {"text": "用户说第1条", "source_message_ids": [first]},
            {"text": "编造的出处", "source_message_ids": [first + 999]},
        ]
    )

    assert run_summary(db_session, task.id, gateway) == "saved"
    loaded = load_summary(db_session, task.conversation_id)
    assert loaded.summary["items"] == [
        {"text": "用户说第1条", "source_message_ids": [first]}
    ]
    # Messages 1-4 left the window of eight.
    assert loaded.summary["covered_through"] == ids[3]
    assert loaded.summary["incremental_count"] == 1
    call = db_session.query(ModelCallRecord).filter_by(task_id=task.id).one()
    assert (call.node_name, call.context_policy) == ("summary", "summary/1")

    # Nothing new has left the window, so the next run calls nothing.
    assert run_summary(db_session, task.id, FakeGateway([])) == "up_to_date"


def test_a_task_without_the_allowance_is_skipped(db_session) -> None:
    budget = {k: v for k, v in BUDGET.items() if k != "summary_max_calls"}
    task = _task(db_session, 12, budget=budget)
    assert run_summary(db_session, task.id, FakeGateway([])) == "skipped"


def test_a_spent_allowance_leaves_the_summary_as_it_was(db_session) -> None:
    task = _task(db_session, 12, budget={**BUDGET, "summary_max_calls": 0})

    assert run_summary(db_session, task.id, FakeGateway([])) == (
        "model_budget_exhausted"
    )
    assert load_summary(db_session, task.conversation_id).version == 0


def test_every_few_updates_the_summary_is_rebuilt(db_session) -> None:
    task = _task(db_session, 12)
    first = _ids(db_session, task)[0]
    set_tenant_scope(db_session, task.company_id)
    old = empty_summary()
    old["items"] = [{"text": "旧要点", "source_message_ids": [first]}]
    old["incremental_count"] = REWRITE_EVERY
    save_summary(
        db_session,
        conversation_id=task.conversation_id,
        company_id=task.company_id,
        summary=old,
        expected_version=0,
    )
    gateway = FakeGateway([{"text": "重写", "source_message_ids": [first]}])

    assert run_summary(db_session, task.id, gateway) == "saved"
    # A rebuild starts from no items and sees every message outside the window.
    assert "旧要点" not in gateway.prompts[0]
    assert gateway.prompts[0].count('"role"') == 4
    loaded = load_summary(db_session, task.conversation_id)
    assert loaded.summary["incremental_count"] == 0
    assert loaded.summary["items"] == [{"text": "重写", "source_message_ids": [first]}]


@pytest.mark.parametrize(
    "mode, conversation_id, budget, queued",
    [
        ("shadow", 5, BUDGET, True),
        ("off", 5, BUDGET, False),
        ("shadow", None, BUDGET, False),
        ("shadow", 5, {"max_calls": 8}, False),
    ],
)
def test_a_publish_queues_the_summary_only_when_it_may_run(
    monkeypatch, mode, conversation_id, budget, queued
) -> None:
    monkeypatch.setattr(get_settings(), "conversation_summary_mode", mode)
    sent: list[dict] = []
    monkeypatch.setattr(
        summary_tasks.summarize_conversation, "delay", lambda **kw: sent.append(kw)
    )
    record = SimpleNamespace(
        id=9, conversation_id=conversation_id, model_budget_snapshot=budget
    )
    tasks._queue_summary(record)  # type: ignore[arg-type]

    assert sent == ([{"task_id": 9}] if queued else [])
