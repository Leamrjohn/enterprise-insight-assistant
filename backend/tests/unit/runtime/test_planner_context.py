"""C4b: shadow records what the engine would send; enforce sends it or asks back."""

import pytest
from app.core.settings import get_settings
from app.modules.analysis.planner.planning import PlanningService
from app.modules.runtime import model_governance
from app.modules.runtime.context.compressors import (
    ASSISTANT_REPLY_CHARS,
    HISTORY_RECENT_MESSAGES,
    compress_history,
)

DECISION = (
    '{"action":"analyze","route":"hybrid","reason":"需要核对数据和资料",'
    '"clarification_question":null,"response_message":null,'
    '"resolved_question":"分析华东区销售额下降原因。"}'
)
QUESTION = "华东区销售额为什么下降？"


class RecordingGateway:
    """Keeps each prompt and the manifest the ledger would record with it."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = responses or [DECISION]
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls.append(
            {"prompt": prompt, "manifest": model_governance._context_manifest.get()}
        )
        return self.responses[len(self.calls) - 1]


def _messages(count: int, content: str = "上一轮问的是华北") -> list[dict]:
    return [
        {"id": i, "role": "user" if i % 2 else "assistant", "content": f"{i}:{content}"}
        for i in range(count)
    ]


LONG_REPLY = "华东区销售额环比变化的原因包括季节性和大客户暂停采购。" * 10
CONSTRAINT = "后面都只看华东区"


def _long_conversation(turns: int, constraint_at: int | None = None) -> list[dict]:
    """Short user turns and long assistant replies; a scope may sit in any turn."""
    messages = []
    for turn in range(turns):
        question = (
            CONSTRAINT if turn == constraint_at else f"第{turn}轮：报告在哪里看？"
        )
        messages += [
            {"id": 2 * turn, "role": "user", "content": question},
            {
                "id": 2 * turn + 1,
                "role": "assistant",
                "content": f"{turn}:{LONG_REPLY}",
            },
        ]
    return messages


def _plan(mode: str, monkeypatch, **context) -> dict:
    monkeypatch.setattr(get_settings(), "context_planner_mode", mode)
    gateway = RecordingGateway()
    PlanningService(gateway=gateway).decide(
        context.pop("question", QUESTION), **context
    )
    assert len(gateway.calls) == 1
    return gateway.calls[0]


def _actions(manifest) -> dict:
    return {entry.name: (entry.action, entry.reason) for entry in manifest.sections}


def test_compress_history_shortens_older_replies_and_keeps_every_user_turn():
    context = {
        "messages": _long_conversation(4, constraint_at=0),
        "history_truncated": False,
        "standing_constraints": ["只看华东区"],
    }
    shrunk = compress_history(context)
    older, recent = (
        shrunk["messages"][:-HISTORY_RECENT_MESSAGES],
        shrunk["messages"][-HISTORY_RECENT_MESSAGES:],
    )
    assert [m["content"] for m in shrunk["messages"] if m["role"] == "user"] == [
        m["content"] for m in context["messages"] if m["role"] == "user"
    ]
    assert all(
        len(m["content"]) == ASSISTANT_REPLY_CHARS and m["content_truncated"]
        for m in older
        if m["role"] == "assistant"
    )
    assert recent == context["messages"][-HISTORY_RECENT_MESSAGES:]
    assert shrunk["history_truncated"] is True
    assert shrunk["standing_constraints"] == ["只看华东区"]
    assert len(context["messages"][1]["content"]) > ASSISTANT_REPLY_CHARS  # unchanged


@pytest.mark.parametrize(
    "context",
    [
        None,
        "not a dict",
        {"messages": []},
        {"messages": _messages(10)},  # every reply already short
        {"messages": _long_conversation(1)},  # only the latest exchange
    ],
)
def test_compress_history_leaves_short_or_odd_history_alone(context):
    assert compress_history(context) is context


def test_shadow_sends_exactly_the_prompt_off_sends(monkeypatch):
    context = {
        "conversation_context": {"version": "2.0", "messages": _messages(3)},
        "planner_memory": [{"content": "常看华东区"}],
        "feedback": {"code": "DATA_EMPTY"},
    }
    off = _plan("off", monkeypatch, **dict(context))
    shadow = _plan("shadow", monkeypatch, **dict(context))
    assert shadow["prompt"] == off["prompt"]
    assert off["manifest"] is None
    assert shadow["manifest"].policy == "planner/3:shadow"


def test_shadow_records_the_whitelist_on_history(monkeypatch):
    conversation = {
        "version": "2.0",
        "messages": _messages(2),
        "history_truncated": False,
        "context_manifest": {"version": "conversation-context/v2", "limits": {}},
    }
    call = _plan("shadow", monkeypatch, conversation_context=conversation)
    actions = _actions(call["manifest"])
    assert actions["history"] == ("filtered", "field_whitelist")
    assert actions["question"] == ("kept", None)
    assert "memory" not in actions  # nothing given, so nothing recorded


def test_shadow_shows_a_long_history_would_be_shortened(monkeypatch):
    conversation = {"messages": _long_conversation(4)}
    call = _plan("shadow", monkeypatch, conversation_context=conversation)
    assert _actions(call["manifest"])["history"] == ("compressed", "near_budget")
    assert call["manifest"].over_budget is False
    assert LONG_REPLY in call["prompt"]  # shadow: the full history is still sent


def test_shadow_shows_memory_would_be_dropped_first(monkeypatch):
    memory = [{"content": "常看华东区销售额" * 60} for _ in range(6)]
    call = _plan("shadow", monkeypatch, planner_memory=memory)
    assert _actions(call["manifest"])["memory"] == ("dropped", "over_budget")
    assert call["manifest"].over_budget is False


def test_shadow_shows_an_oversized_question_would_be_asked_back(monkeypatch):
    call = _plan("shadow", monkeypatch, question="问" * 3000)
    assert call["manifest"].over_budget is True
    assert "问" * 3000 in call["prompt"]  # shadow never blocks the call


def test_enforce_sends_the_old_prompt_when_nothing_needs_cutting(monkeypatch):
    context = {
        "conversation_context": {"messages": _messages(3), "history_truncated": False},
        "planner_memory": [{"content": "常看华东区"}],
    }
    off = _plan("off", monkeypatch, **dict(context))
    enforce = _plan("enforce", monkeypatch, **dict(context))
    assert enforce["prompt"] == off["prompt"]
    assert enforce["manifest"].policy == "planner/3"


def test_enforce_leaves_the_selection_record_out_of_the_prompt(monkeypatch):
    conversation = {
        "version": "2.0",
        "messages": _messages(2),
        "context_manifest": {"version": "conversation-context/v2", "limits": {}},
    }
    call = _plan("enforce", monkeypatch, conversation_context=conversation)
    assert "conversation-context/v2" not in call["prompt"]
    assert "1:上一轮问的是华北" in call["prompt"]


def test_enforce_keeps_a_recent_scope_that_never_reached_standing_constraints(
    monkeypatch,
):
    """The C4 regression: dropping turns lost a scope said within the last 8."""
    conversation = {"messages": _long_conversation(4, constraint_at=0)}
    call = _plan("enforce", monkeypatch, conversation_context=conversation)
    assert _actions(call["manifest"])["history"] == ("compressed", "near_budget")
    assert CONSTRAINT in call["prompt"]
    assert f"3:{LONG_REPLY}" in call["prompt"]  # the latest reply stays whole
    assert f"0:{LONG_REPLY}" not in call["prompt"]
    assert '"history_truncated": true' in call["prompt"]


def test_enforce_drops_memory_before_giving_up(monkeypatch):
    memory = [{"content": "常看华东区销售额" * 60} for _ in range(6)]
    call = _plan("enforce", monkeypatch, planner_memory=memory)
    assert "常看华东区销售额" not in call["prompt"]
    assert "<planner_memory>\n[]\n</planner_memory>" in call["prompt"]


def test_enforce_asks_back_without_calling_the_model(monkeypatch):
    monkeypatch.setattr(get_settings(), "context_planner_mode", "enforce")
    gateway = RecordingGateway()
    service = PlanningService(gateway=gateway)
    decision = service.decide("问" * 3000)
    assert gateway.calls == []
    assert service.model_attempts == 0
    assert decision.action == "needs_clarification"
    assert decision.clarification_question == "问题或对话太长，请缩小范围后再问。"


def test_enforce_repair_prompt_uses_what_was_kept(monkeypatch):
    monkeypatch.setattr(get_settings(), "context_planner_mode", "enforce")
    gateway = RecordingGateway(["not json", DECISION])
    conversation = {
        "messages": _messages(2),
        "context_manifest": {"version": "conversation-context/v2"},
    }
    PlanningService(gateway=gateway).decide(QUESTION, conversation_context=conversation)
    assert len(gateway.calls) == 2
    assert "conversation-context/v2" not in gateway.calls[1]["prompt"]
    assert gateway.calls[1]["manifest"].policy == "planner/3"
