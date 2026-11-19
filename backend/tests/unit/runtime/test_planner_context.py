"""C4b: the Planner records what the engine would send, and still sends the old prompt."""

import pytest
from app.core.settings import get_settings
from app.modules.analysis.planner.planning import PlanningService
from app.modules.runtime import model_governance
from app.modules.runtime.context.compressors import (
    HISTORY_KEEP_MESSAGES,
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

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls.append(
            {"prompt": prompt, "manifest": model_governance._context_manifest.get()}
        )
        return DECISION


def _messages(count: int, content: str = "上一轮问的是华北") -> list[dict]:
    return [
        {"id": i, "role": "user" if i % 2 else "assistant", "content": f"{i}:{content}"}
        for i in range(count)
    ]


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


def test_compress_history_keeps_the_latest_turns_and_says_so():
    context = {
        "messages": _messages(10),
        "history_truncated": False,
        "standing_constraints": ["只看华东区"],
    }
    shrunk = compress_history(context)
    assert shrunk["messages"] == context["messages"][-HISTORY_KEEP_MESSAGES:]
    assert shrunk["history_truncated"] is True
    assert shrunk["standing_constraints"] == ["只看华东区"]
    assert len(context["messages"]) == 10  # the original is not changed


@pytest.mark.parametrize(
    "context",
    [
        None,
        "not a dict",
        {"messages": []},
        {"messages": _messages(HISTORY_KEEP_MESSAGES)},
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
    assert shadow["manifest"].policy == "planner/1:shadow"


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


def test_shadow_shows_a_long_history_would_be_cut(monkeypatch):
    conversation = {"messages": _messages(12, "华东区销售额环比变化" * 30)}
    call = _plan("shadow", monkeypatch, conversation_context=conversation)
    assert _actions(call["manifest"])["history"] == ("compressed", "near_budget")
    assert call["manifest"].over_budget is False
    assert "0:华东区" in call["prompt"]  # shadow: the full history is still sent


def test_shadow_shows_memory_would_be_dropped_first(monkeypatch):
    memory = [{"content": "常看华东区销售额" * 60} for _ in range(6)]
    call = _plan("shadow", monkeypatch, planner_memory=memory)
    assert _actions(call["manifest"])["memory"] == ("dropped", "over_budget")
    assert call["manifest"].over_budget is False


def test_shadow_shows_an_oversized_question_would_be_asked_back(monkeypatch):
    call = _plan("shadow", monkeypatch, question="问" * 3000)
    assert call["manifest"].over_budget is True
    assert "问" * 3000 in call["prompt"]  # shadow never blocks the call
