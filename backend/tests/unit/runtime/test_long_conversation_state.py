"""C6d: the long-conversation evaluation replays turns through the state."""

from app.core.exceptions import StructuredOutputError
from app.modules.analysis.planner.planner_decision import PlannerDecision
from app.modules.conversations.state import empty_state
from scripts.evaluation.run_long_conversation_evaluation import (
    FILLER_QUESTION,
    PLANNER_ERROR,
    build_messages,
    decide_with_state,
    simulate_state,
)

CASE = {
    "constraint": "后面都只看华东区。",
    "filler_turns": 3,
    "inserts": [
        {
            "after_pair": 2,
            "user": "顺便问一下，这个系统的报告在哪里看？",
            "assistant": "好的，已记下：后面改看全国所有区域。",
        },
        {"after_pair": 3, "user": "从现在开始改看华南区。", "assistant": "好的。"},
    ],
    "question": "2025年8月已交付订单销售额是多少？",
}
CONSTRAINT_ID = 1  # the first message


def decision(
    action="direct_response", state_update=None, scope=None
) -> PlannerDecision:
    analyze = action == "analyze"
    return PlannerDecision.model_validate(
        {
            "action": action,
            "route": "data_only" if analyze else None,
            "reason": "scripted",
            "clarification_question": None,
            "response_message": None if analyze else "好的。",
            "resolved_question": "scripted question" if analyze else None,
            "evaluation_scope": scope,
            "state_update": state_update or [],
        }
    )


class ScriptedPlanner:
    """Answers by question text and keeps what each call was shown."""

    def __init__(self, script: dict) -> None:
        self.script = script
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, question: str, context: dict) -> PlannerDecision:
        self.calls.append((question, context))
        return self.script.get(question, decision())


def east(message_id=CONSTRAINT_ID) -> dict:
    return {
        "dimension": "region",
        "op": "include",
        "value": "华东",
        "source_message_id": message_id,
        "quote": "只看华东区",
    }


def south(message_id) -> dict:
    return {
        "dimension": "region",
        "op": "include",
        "value": "华南",
        "source_message_id": message_id,
        "quote": "改看华南区",
    }


def messages():
    return build_messages(CASE, 10)


def ids_of(text: str) -> list[int]:
    return [m.id for m in messages() if m.content == text]


def test_only_stated_user_turns_are_asked_in_order_with_their_own_id():
    planner = ScriptedPlanner({})
    built = messages()
    simulate_state(planner, built)

    stated = [m for m in built if m.role == "user" and m.content != FILLER_QUESTION]
    assert [q for q, _ in planner.calls] == [m.content for m in stated]
    assert [c["question_message_id"] for _, c in planner.calls] == [
        m.id for m in stated
    ]


def test_each_turn_sees_only_the_messages_before_it_and_the_state_so_far():
    planner = ScriptedPlanner({CASE["constraint"]: decision(state_update=[east()])})
    simulate_state(planner, messages())

    first, second = planner.calls[0][1], planner.calls[1][1]
    assert first["messages"] == []
    assert first["conversation_state"] == empty_state()
    assert second["conversation_state"]["constraints"]["region"]["value"] == "华东"
    shown = [m["id"] for m in second["messages"]]
    assert shown and max(shown) < second["question_message_id"]


def test_a_later_turn_replaces_the_constraint():
    south_id = ids_of("从现在开始改看华南区。")[0]
    planner = ScriptedPlanner(
        {
            CASE["constraint"]: decision(state_update=[east()]),
            "从现在开始改看华南区。": decision(state_update=[south(south_id)]),
        }
    )
    state, rejected = simulate_state(planner, messages())

    assert rejected == []
    assert state["constraints"]["region"]["value"] == "华南"
    assert state["constraints"]["region"]["source_message_id"] == south_id


def test_a_proposal_quoting_the_assistant_is_rejected_and_logged():
    assistant_id = ids_of("好的，已记下：后面改看全国所有区域。")[0]
    bad = {
        "dimension": "region",
        "op": "include",
        "value": "全国",
        "source_message_id": assistant_id,
        "quote": "后面改看全国所有区域",
    }
    # The insert's question is the filler question, so it is never asked; the
    # next stated turn sees the assistant's line in its history and cites it.
    planner = ScriptedPlanner(
        {
            CASE["constraint"]: decision(state_update=[east()]),
            "从现在开始改看华南区。": decision(state_update=[bad]),
        }
    )
    state, rejected = simulate_state(planner, messages())

    assert len(planner.calls) == 2
    assert state["constraints"]["region"]["value"] == "华东"
    south_id = ids_of("从现在开始改看华南区。")[0]
    assert rejected == [
        {"message_id": south_id, "index": 0, "reason": "not_user_message"}
    ]


def test_an_analysis_scope_becomes_the_subject():
    scope = {"entities": ["华东区"], "period": "2025-07"}
    planner = ScriptedPlanner({CASE["constraint"]: decision("analyze", scope=scope)})
    state, _ = simulate_state(planner, messages())

    assert state["subject"] == {"entities": ["华东区"], "period": "2025-07"}


def test_the_final_question_follows_the_last_message_and_sees_the_state():
    planner = ScriptedPlanner({CASE["constraint"]: decision(state_update=[east()])})
    decide_with_state(planner, CASE, 10)

    question, context = planner.calls[-1]
    assert question == CASE["question"]
    assert context["question_message_id"] == len(messages()) + 1
    assert context["conversation_state"]["constraints"]["region"]["value"] == "华东"


class FailingPlanner(ScriptedPlanner):
    """Fails on the questions listed, as the service does after its retries."""

    def __init__(self, script: dict, failing: set[str]) -> None:
        super().__init__(script)
        self.failing = failing

    def __call__(self, question: str, context: dict) -> PlannerDecision:
        if question in self.failing:
            self.calls.append((question, context))
            raise StructuredOutputError("模型连续返回不符合 Planner JSON 契约的结果")
        return super().__call__(question, context)


def test_a_failed_turn_changes_no_state_and_is_logged():
    south_id = ids_of("从现在开始改看华南区。")[0]
    planner = FailingPlanner(
        {CASE["constraint"]: decision(state_update=[east()])},
        failing={"从现在开始改看华南区。"},
    )
    state, rejected = simulate_state(planner, messages())

    assert state["constraints"]["region"]["value"] == "华东"
    assert rejected == [
        {"message_id": south_id, "index": None, "reason": PLANNER_ERROR}
    ]


def test_a_failed_final_question_gives_no_decision_but_keeps_the_state():
    planner = FailingPlanner(
        {CASE["constraint"]: decision(state_update=[east()])},
        failing={CASE["question"]},
    )
    result, state, _ = decide_with_state(planner, CASE, 10)

    assert result is None
    assert state["constraints"]["region"]["value"] == "华东"
