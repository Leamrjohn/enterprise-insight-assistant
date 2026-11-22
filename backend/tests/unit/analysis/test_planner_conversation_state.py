"""C6g: the Planner reads the conversation state and keeps its nine fields."""

import hashlib
import json

import pytest
from app.core.settings import get_settings
from app.modules.analysis.planner.planner_decision import PlannerDecision
from app.modules.analysis.planner.planning import (
    PlanningService,
    build_planning_repair_prompt,
    build_planning_system_prompt,
    build_planning_user_prompt,
)
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
    "resolved_question": "华东区2025年8月销售额是多少？",
}
WITH_STATE = {**CONTEXT, "conversation_state": STATE}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


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


def test_a_state_adds_a_read_only_note():
    prompt = build_planning_user_prompt(QUESTION, WITH_STATE)

    assert "conversation_context.conversation_state" in prompt
    assert json.dumps(STATE, ensure_ascii=False) in prompt
    assert "必须写进 resolved_question 和 evaluation_scope" in prompt
    # Proposing changes is the extractor's job now (C6f).
    assert "state_update" not in prompt
    assert "消息 id" not in prompt


def test_the_repair_prompt_keeps_the_note_and_asks_for_nine_fields():
    with pytest.raises(ValidationError) as error:
        PlannerDecision.model_validate({"action": "analyze"})
    for context in (WITH_STATE, CONTEXT):
        prompt = build_planning_repair_prompt(QUESTION, context, "{}", error.value)
        assert "完整的九字段 JSON" in prompt
        assert "state_update" not in prompt
    with_state = build_planning_repair_prompt(QUESTION, WITH_STATE, "{}", error.value)
    assert "conversation_context.conversation_state" in with_state


def test_a_stray_state_update_from_the_model_is_ignored():
    proposal = {"dimension": "region", "op": "clear", "value": None}
    decision = PlannerDecision.model_validate({**DECISION, "state_update": [proposal]})

    assert decision.action == "analyze"
    assert "state_update" not in decision.model_dump()


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        manifest = model_governance._context_manifest.get()
        self.calls.append({"prompt": prompt, "manifest": manifest})
        return json.dumps(DECISION, ensure_ascii=False)


def test_enforce_keeps_the_state_but_not_a_question_id(monkeypatch):
    monkeypatch.setattr(get_settings(), "context_planner_mode", "enforce")
    gateway = RecordingGateway()
    PlanningService(gateway=gateway).decide(
        QUESTION, conversation_context={**WITH_STATE, "question_message_id": 42}
    )

    prompt = gateway.calls[0]["prompt"]
    assert gateway.calls[0]["manifest"].policy == "planner/4"
    assert '"conversation_state"' in prompt
    assert "question_message_id" not in prompt
