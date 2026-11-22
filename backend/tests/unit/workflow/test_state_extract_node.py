"""M7: the workflow extracts the state before planning and saves it at publish."""

import json
from types import SimpleNamespace

import pytest
from app.core.exceptions import RetryableModelError
from app.core.settings import get_settings
from app.modules.conversations.state import STATE_SNAPSHOT_KEY, empty_state
from app.modules.conversations.state_extractor import MODEL_ERROR
from app.modules.workflow import tasks
from app.modules.workflow.orchestration import graph, nodes

QUESTION = "从现在开始改看华南区，8月销售额是多少？"
MESSAGES = [
    {
        "id": 1,
        "role": "user",
        "content": "后面都只看华东区。",
        "content_truncated": False,
    },
    {
        "id": 2,
        "role": "assistant",
        "content": "好的，已记下：以后看全国。",
        "content_truncated": False,
    },
]
EAST = {"op": "include", "value": "华东", "source_message_id": 1, "quote": "只看华东区"}
SOUTH = {
    "dimension": "region",
    "op": "include",
    "value": "华南",
    "source_message_id": 3,
    "quote": "改看华南区",
}
ASSISTANT = {
    "dimension": "region",
    "op": "include",
    "value": "全国",
    "source_message_id": 2,
    "quote": "以后看全国",
}


def frozen_state() -> dict:
    state = empty_state()
    state["constraints"]["region"] = dict(EAST)
    return state


def context(with_state: bool = True) -> dict:
    ctx = {
        "version": "2.0",
        "messages": MESSAGES,
        "history_truncated": True,
        "standing_constraints": [{"id": 1, "content": "后面都只看华东区。"}],
    }
    if with_state:
        ctx[STATE_SNAPSHOT_KEY] = {
            "state": frozen_state(),
            "version": 4,
            "message_id": 3,
        }
    return ctx


class FakeGateway:
    def __init__(self, updates=None, error=None) -> None:
        self.updates = updates or []
        self.error = error
        self.calls = 0

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return json.dumps({"state_update": self.updates}, ensure_ascii=False)


def run_node(monkeypatch, gateway, ctx) -> tuple[dict, list]:
    monkeypatch.setattr(nodes, "get_model_gateway", lambda: gateway)
    checkpoints: list = []
    update = nodes.state_extract_node(
        {
            "question": QUESTION,
            "conversation_context": ctx,
            "checkpoint_callback": lambda *args: checkpoints.append(args),
        }  # type: ignore[typeddict-item]
    )
    return update, checkpoints


def test_without_a_frozen_state_nothing_is_called(monkeypatch):
    gateway = FakeGateway()
    update, checkpoints = run_node(monkeypatch, gateway, context(with_state=False))

    assert update == {}
    assert gateway.calls == 0
    assert checkpoints == []


def test_checked_proposals_become_the_state_and_are_checkpointed(monkeypatch):
    gateway = FakeGateway([SOUTH, ASSISTANT])
    update, checkpoints = run_node(monkeypatch, gateway, context())

    region = update["conversation_state"]["constraints"]["region"]
    assert (region["value"], region["source_message_id"]) == ("华南", 3)
    assert update["state_extraction"] == {
        "error": None,
        "proposed": 2,
        "rejected": [{"index": 1, "reason": "not_user_message"}],
    }
    ((completed, next_node, saved),) = checkpoints
    assert (completed, next_node) == ("state_extract_node", "planner_node")
    assert saved["conversation_state"] == update["conversation_state"]


def test_a_failed_extraction_keeps_the_frozen_state(monkeypatch):
    gateway = FakeGateway(error=RetryableModelError("timeout"))
    update, _ = run_node(monkeypatch, gateway, context())

    assert update["conversation_state"] == frozen_state()
    assert update["state_extraction"]["error"] == MODEL_ERROR


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_off_and_shadow_hide_the_state_from_the_planner(monkeypatch, mode):
    monkeypatch.setattr(get_settings(), "conversation_state_mode", mode)
    planned = nodes._planner_conversation_context(
        {"conversation_context": context(), "conversation_state": frozen_state()}  # type: ignore[typeddict-item]
    )

    assert planned == context(with_state=False)


def test_enforce_swaps_the_regex_constraints_for_the_state(monkeypatch):
    monkeypatch.setattr(get_settings(), "conversation_state_mode", "enforce")
    extracted = frozen_state()
    planned = nodes._planner_conversation_context(
        {"conversation_context": context(), "conversation_state": extracted}  # type: ignore[typeddict-item]
    )

    expected = context(with_state=False)
    del expected["standing_constraints"]
    assert planned == {**expected, "conversation_state": extracted}


def test_a_context_without_a_frozen_state_is_passed_unchanged(monkeypatch):
    monkeypatch.setattr(get_settings(), "conversation_state_mode", "enforce")
    ctx = context(with_state=False)
    assert nodes._planner_conversation_context({"conversation_context": ctx}) is ctx  # type: ignore[typeddict-item]


def test_a_new_run_starts_with_the_extractor_and_old_checkpoints_still_resume():
    assert graph._route_from_start({"resume_next_node": None}) == "state_extract_node"  # type: ignore[typeddict-item]
    assert (
        graph._route_from_start({"resume_next_node": "planner_node"}) == "planner_node"
    )  # type: ignore[typeddict-item]


def task(snapshot: dict | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=9, conversation_id=5, company_id=7, context_snapshot=snapshot
    )


def test_publish_saves_with_the_frozen_version(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(tasks, "save_state", lambda db, **kw: calls.append(kw) or True)
    tasks._save_conversation_state(None, task(context()), frozen_state())

    assert calls == [
        {
            "conversation_id": 5,
            "company_id": 7,
            "state": frozen_state(),
            "expected_version": 4,
            "task_id": 9,
        }
    ]


@pytest.mark.parametrize(
    "record, state",
    [(task(context()), None), (task(context(with_state=False)), frozen_state())],
)
def test_publish_saves_nothing_without_a_frozen_or_new_state(
    monkeypatch, record, state
):
    calls: list = []
    monkeypatch.setattr(tasks, "save_state", lambda db, **kw: calls.append(kw))
    tasks._save_conversation_state(None, record, state)

    assert calls == []
