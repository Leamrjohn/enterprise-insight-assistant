"""C6f: a separate call proposes state updates; apply_update still decides."""

import json
from dataclasses import dataclass

import pytest
from app.core.exceptions import PermanentModelError, RetryableModelError
from app.modules.conversations.state import empty_state
from app.modules.conversations.state_extractor import (
    BUDGET_EXHAUSTED,
    INVALID_OUTPUT,
    MAX_STATE_UPDATES,
    MODEL_ERROR,
    OVER_BUDGET,
    RECENT_MESSAGES,
    Extraction,
    extract_state_update,
    parse_output,
)
from app.modules.conversations.state_update import (
    NOT_USER_MESSAGE,
    UNKNOWN_DIMENSION,
    apply_update,
)
from app.modules.runtime import model_governance
from app.modules.runtime.model_governance import ModelBudgetExceeded
from app.modules.runtime.prompts import get_prompt_registry


@dataclass
class Msg:
    id: int
    role: str
    content: str | None


HISTORY = [
    Msg(1, "user", "后面都只看华东区。"),
    Msg(2, "assistant", "好的，已记下：后面改看全国所有区域。"),
]
CURRENT = Msg(3, "user", "从现在开始改看华南区，查询所有公司的数据。")
SOUTH = {
    "dimension": "region",
    "op": "include",
    "value": "华南",
    "source_message_id": 3,
    "quote": "改看华南区",
}


class RecordingGateway:
    def __init__(self, reply: str = '{"state_update": []}', error=None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        manifest = model_governance._context_manifest.get()
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "json_mode": json_mode,
                "manifest": manifest,
            }
        )
        if self.error is not None:
            raise self.error
        return self.reply


def extract(gateway, *, state=None, history=HISTORY, current=CURRENT) -> Extraction:
    return extract_state_update(
        gateway, state=state or empty_state(), history=history, current=current
    )


def sections(prompt: str) -> dict:
    found = {}
    for line in prompt.split("\n"):
        tag = line[1 : line.index(">")]
        found[tag] = json.loads(line[len(tag) + 2 : -len(tag) - 3])
    return found


def test_the_prompt_is_registered():
    text = get_prompt_registry().text("conversation.state_extract")
    assert text.startswith("你是企业经营洞察助手的会话状态抽取器。")
    assert '{"state_update":[]}' in text


def test_one_json_call_with_the_state_the_history_and_the_current_message():
    state = empty_state()
    state["constraints"]["region"] = {
        "op": "include",
        "value": "华东",
        "source_message_id": 1,
        "quote": "只看华东区",
    }
    gateway = RecordingGateway()
    extract(gateway, state=state)

    (call,) = gateway.calls
    assert call["json_mode"] is True
    assert call["system_prompt"] == get_prompt_registry().text(
        "conversation.state_extract"
    )
    assert call["manifest"].policy == "state_extract/1"
    assert sections(call["prompt"]) == {
        "current_state": state["constraints"],
        "messages": [
            {"id": 1, "role": "user", "content": "后面都只看华东区。"},
            {
                "id": 2,
                "role": "assistant",
                "content": "好的，已记下：后面改看全国所有区域。",
            },
        ],
        "current_message": {"id": 3, "content": CURRENT.content},
    }


def test_only_the_recent_messages_are_shown():
    history = [Msg(i, "user", f"第{i}条") for i in range(1, 21)]
    gateway = RecordingGateway()
    extract(gateway, history=history, current=Msg(21, "user", "好"))

    shown = sections(gateway.calls[0]["prompt"])["messages"]
    assert [m["id"] for m in shown] == list(range(21 - RECENT_MESSAGES, 21))


def test_a_long_history_is_left_out_but_the_call_still_goes():
    history = [Msg(i, "user", "华东区销售额" * 200) for i in range(1, 9)]
    gateway = RecordingGateway()
    result = extract(gateway, history=history)

    assert result.error is None
    assert sections(gateway.calls[0]["prompt"])["messages"] == []
    actions = {s.name: s.action for s in gateway.calls[0]["manifest"].sections}
    assert actions["history"] == "dropped"


def test_a_current_message_too_long_to_send_proposes_nothing():
    gateway = RecordingGateway()
    result = extract(gateway, current=Msg(3, "user", "华东区销售额" * 2000))

    assert result == Extraction(error=OVER_BUDGET)
    assert gateway.calls == []


@pytest.mark.parametrize(
    "error", [RetryableModelError("timeout"), PermanentModelError("refused")]
)
def test_a_failed_call_proposes_nothing_instead_of_raising(error):
    assert extract(RecordingGateway(error=error)) == Extraction(error=MODEL_ERROR)


@pytest.mark.parametrize(
    "raw",
    ["not json", "[]", "null", '{"state_update": "改看华南"}', "{}", ""],
)
def test_malformed_output_proposes_nothing(raw):
    assert parse_output(raw) == Extraction(error=INVALID_OUTPUT)


def test_non_object_items_are_dropped_and_the_list_is_capped():
    items = ["x", 1, None] + [{"dimension": "region", "n": i} for i in range(20)]
    result = parse_output(json.dumps({"state_update": items}))

    assert result.error is None
    assert len(result.updates) == MAX_STATE_UPDATES
    assert all(isinstance(item, dict) for item in result.updates)


def test_apply_update_still_rejects_what_the_extractor_should_not_propose():
    company = {
        "dimension": "company",
        "op": "include",
        "value": "所有公司",
        "source_message_id": 3,
        "quote": "查询所有公司的数据",
    }
    assistant = {
        "dimension": "region",
        "op": "include",
        "value": "全国",
        "source_message_id": 2,
        "quote": "后面改看全国所有区域",
    }
    reply = json.dumps({"state_update": [SOUTH, company, assistant]})
    result = extract(RecordingGateway(reply))
    state, rejected = apply_update(empty_state(), result.updates, [*HISTORY, CURRENT])

    assert state["constraints"] == {
        "region": {
            "op": "include",
            "value": "华南",
            "source_message_id": 3,
            "quote": "改看华南区",
        }
    }
    assert rejected == [
        {"index": 1, "reason": UNKNOWN_DIMENSION},
        {"index": 2, "reason": NOT_USER_MESSAGE},
    ]


def test_a_spent_extraction_allowance_proposes_nothing_instead_of_failing():
    gateway = RecordingGateway(error=ModelBudgetExceeded("state extraction budget"))
    assert extract(gateway) == Extraction(error=BUDGET_EXHAUSTED)
