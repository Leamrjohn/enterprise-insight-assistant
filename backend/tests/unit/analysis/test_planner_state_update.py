"""C6c: the Planner proposes state updates only when it is shown a state."""

import hashlib
import json

import pytest
from app.core.settings import get_settings
from app.modules.analysis.planner.planner_decision import (
    MAX_STATE_UPDATES,
    PlannerDecision,
)
from app.modules.analysis.planner.planning import (
    STATE_DIMENSIONS,
    PlanningService,
    build_planning_repair_prompt,
    build_planning_system_prompt,
    build_planning_user_prompt,
)
from app.modules.conversations.state_update import DIMENSIONS
from app.modules.runtime import model_governance
from pydantic import ValidationError

QUESTION = "2025年8月销售额是多少？"
CONTEXT = {
    "version": "2.0",
    "messages": [
        {
            "id": 1,
            "role": "user",
            "content": "华东区8月销售额",
            "content_truncated": False,
        }
    ],
    "history_truncated": True,
    "standing_constraints": [{"id": 1, "content": "后面都只看华东区。"}],
}
STATE = {
    "schema": "conversation-state/v1",
    "subject": {"entities": ["华东区"], "period": "2025-08"},
    "constraints": {
        "region": {
            "op": "include",
            "value": "华东",
            "source_message_id": 1,
            "quote": "只看华东区",
        }
    },
    "open_question": None,
}
DECISION = {
    "action": "analyze",
    "route": "data_only",
    "reason": "查询销售额",
    "clarification_question": None,
    "response_message": None,
    "resolved_question": "华南区2025年8月销售额是多少？",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def with_state(question_message_id: int = 7) -> dict:
    return {
        **CONTEXT,
        "conversation_state": STATE,
        "question_message_id": question_message_id,
    }


def test_prompts_without_a_state_are_byte_identical_to_before():
    # Hashes taken on the code before C6c.
    assert sha(build_planning_system_prompt()) == (
        "7a5d73565d75919e7672ed9a5629f5e5034631a68007433c4792a03e33379502"
    )
    assert sha(build_planning_user_prompt(QUESTION, None)) == (
        "8160ccd931e591ac1a80a64156a2a7ff4f07863159294ce1b05bd1b6a792a9c9"
    )
    assert sha(build_planning_user_prompt(QUESTION, CONTEXT)) == (
        "ed36cb0e051e8b6c2519a6d2e1f240e0a2a8dc630536423e7e079e2efdb8af82"
    )


def test_a_state_adds_the_note_with_the_question_id_and_the_dimensions():
    prompt = build_planning_user_prompt(QUESTION, with_state(42))

    assert "conversation_context.conversation_state" in prompt
    assert "当前问题的消息 id 是 42" in prompt
    assert "state_update" in prompt
    assert all(dimension in prompt for dimension in STATE_DIMENSIONS)
    assert json.dumps(STATE, ensure_ascii=False) in prompt


def test_the_note_spells_out_all_ten_fields():
    prompt = build_planning_user_prompt(QUESTION, with_state())
    skeleton = prompt.split("格式为：", 1)[1].split("\n", 1)[0]
    fields = list(json.loads(skeleton))

    assert fields[:9] == [
        "action",
        "route",
        "reason",
        "clarification_question",
        "response_message",
        "resolved_question",
        "clarification",
        "intent",
        "evaluation_scope",
    ]
    assert fields[9] == "state_update"
    assert "只写 include 新值" in prompt
    assert "一次性问题" in prompt


def test_the_repair_prompt_keeps_the_note_and_asks_for_ten_fields():
    with pytest.raises(ValidationError) as error:
        PlannerDecision.model_validate({"action": "analyze"})
    prompt = build_planning_repair_prompt(QUESTION, with_state(), "{}", error.value)
    assert "当前问题的消息 id 是 7" in prompt
    assert "完整的十字段 JSON" in prompt
    without = build_planning_repair_prompt(QUESTION, CONTEXT, "{}", error.value)
    assert "state_update" not in without
    assert "完整的九字段 JSON" in without


def test_the_note_lists_exactly_the_dimensions_code_accepts():
    assert set(STATE_DIMENSIONS) == DIMENSIONS


def test_state_update_defaults_to_empty_and_an_empty_one_is_not_dumped():
    decision = PlannerDecision.model_validate(DECISION)
    assert decision.state_update == []
    assert "state_update" not in decision.model_dump()
    assert "state_update" not in decision.model_dump_json()
    proposal = {"dimension": "region", "op": "clear", "value": None}
    with_one = PlannerDecision.model_validate({**DECISION, "state_update": [proposal]})
    assert with_one.model_dump()["state_update"] == [proposal]
    assert PlannerDecision.model_validate(with_one.model_dump()) == with_one


def test_state_update_proposals_are_kept_for_code_to_check():
    proposal = {
        "dimension": "region",
        "op": "include",
        "value": "华南",
        "source_message_id": 7,
        "quote": "改看华南区",
    }
    decision = PlannerDecision.model_validate({**DECISION, "state_update": [proposal]})
    assert decision.state_update == [proposal]


@pytest.mark.parametrize("junk", [None, "改看华南", {"dimension": "region"}, 3])
def test_a_malformed_state_update_never_fails_the_plan(junk):
    decision = PlannerDecision.model_validate({**DECISION, "state_update": junk})
    assert decision.action == "analyze"
    assert decision.state_update == []


def test_non_object_items_are_dropped_and_the_list_is_capped():
    items = ["x", 1, None] + [{"dimension": "region", "n": i} for i in range(20)]
    decision = PlannerDecision.model_validate({**DECISION, "state_update": items})
    assert len(decision.state_update) == MAX_STATE_UPDATES
    assert all(isinstance(item, dict) for item in decision.state_update)


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        manifest = model_governance._context_manifest.get()
        self.calls.append({"prompt": prompt, "manifest": manifest})
        return json.dumps(DECISION, ensure_ascii=False)


def test_enforce_keeps_the_state_and_the_question_id(monkeypatch):
    monkeypatch.setattr(get_settings(), "context_planner_mode", "enforce")
    gateway = RecordingGateway()
    PlanningService(gateway=gateway).decide(
        QUESTION, conversation_context=with_state(42)
    )

    prompt = gateway.calls[0]["prompt"]
    assert gateway.calls[0]["manifest"].policy == "planner/3"
    assert '"conversation_state"' in prompt
    assert '"question_message_id": 42' in prompt
    assert "当前问题的消息 id 是 42" in prompt
