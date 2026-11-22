"""C6g: the long-conversation evaluation replays turns through the extractor."""

from app.core.exceptions import StructuredOutputError
from app.modules.analysis.planner.planner_decision import PlannerDecision
from app.modules.conversations.state import empty_state
from app.modules.conversations.state_extractor import MODEL_ERROR, Extraction
from scripts.evaluation.run_long_conversation_evaluation import (
    FILLER_QUESTION,
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
SOUTH_TURN = "从现在开始改看华南区。"


def decision() -> PlannerDecision:
    return PlannerDecision.model_validate(
        {
            "action": "analyze",
            "route": "data_only",
            "reason": "scripted",
            "clarification_question": None,
            "response_message": None,
            "resolved_question": "scripted question",
        }
    )


class ScriptedPlanner:
    """Keeps what each call was shown."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, question: str, context: dict) -> PlannerDecision:
        self.calls.append((question, context))
        if self.fail:
            raise StructuredOutputError("模型连续返回不符合 Planner JSON 契约的结果")
        return decision()


class ScriptedExtractor:
    """Answers by message text and keeps what each call was shown."""

    def __init__(self, script: dict) -> None:
        self.script = script
        self.calls: list[tuple[dict, list, object]] = []

    def __call__(self, state: dict, history: list, current) -> Extraction:
        self.calls.append((state, history, current))
        return self.script.get(current.content, Extraction())


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


def id_of(text: str) -> int:
    return next(m.id for m in messages() if m.content == text)


def test_only_stated_user_turns_are_extracted_in_order():
    extractor = ScriptedExtractor({})
    built = messages()
    simulate_state(extractor, built)

    stated = [m for m in built if m.role == "user" and m.content != FILLER_QUESTION]
    assert [current for _, _, current in extractor.calls] == stated


def test_each_turn_sees_only_the_messages_before_it_and_the_state_so_far():
    extractor = ScriptedExtractor({CASE["constraint"]: Extraction([east()])})
    built = messages()
    simulate_state(extractor, built)

    (first_state, first_history, _), (second_state, second_history, second) = (
        extractor.calls[:2]
    )
    assert first_history == []
    assert first_state == empty_state()
    assert second_state["constraints"]["region"]["value"] == "华东"
    assert second_history == built[: built.index(second)]


def test_a_later_turn_replaces_the_constraint():
    south_id = id_of(SOUTH_TURN)
    extractor = ScriptedExtractor(
        {
            CASE["constraint"]: Extraction([east()]),
            SOUTH_TURN: Extraction([south(south_id)]),
        }
    )
    state, rejected = simulate_state(extractor, messages())

    assert rejected == []
    assert state["constraints"]["region"]["value"] == "华南"
    assert state["constraints"]["region"]["source_message_id"] == south_id


def test_a_proposal_quoting_the_assistant_is_rejected_and_logged():
    assistant_id = id_of("好的，已记下：后面改看全国所有区域。")
    bad = {
        "dimension": "region",
        "op": "include",
        "value": "全国",
        "source_message_id": assistant_id,
        "quote": "后面改看全国所有区域",
    }
    extractor = ScriptedExtractor(
        {CASE["constraint"]: Extraction([east()]), SOUTH_TURN: Extraction([bad])}
    )
    state, rejected = simulate_state(extractor, messages())

    assert state["constraints"]["region"]["value"] == "华东"
    assert rejected == [
        {"message_id": id_of(SOUTH_TURN), "index": 0, "reason": "not_user_message"}
    ]


def test_a_failed_extraction_changes_no_state_and_is_logged():
    extractor = ScriptedExtractor(
        {
            CASE["constraint"]: Extraction([east()]),
            SOUTH_TURN: Extraction(error=MODEL_ERROR),
        }
    )
    state, rejected = simulate_state(extractor, messages())

    assert state["constraints"]["region"]["value"] == "华东"
    assert rejected == [
        {"message_id": id_of(SOUTH_TURN), "index": None, "reason": MODEL_ERROR}
    ]


def test_the_final_question_is_extracted_then_planned_once_with_the_state():
    built = messages()
    final_id = len(built) + 1
    extractor = ScriptedExtractor(
        {
            CASE["constraint"]: Extraction([east()]),
            CASE["question"]: Extraction([south(final_id)]),
        }
    )
    planner = ScriptedPlanner()
    result, state, rejected = decide_with_state(planner, extractor, CASE, 10)

    last = extractor.calls[-1][2]
    assert (last.id, last.role, last.content) == (final_id, "user", CASE["question"])
    # The quote is not in the question, so apply_update rejects it.
    assert state["constraints"]["region"]["value"] == "华东"
    assert rejected == [
        {"message_id": final_id, "index": 0, "reason": "quote_not_in_message"}
    ]
    ((question, context),) = planner.calls
    assert question == CASE["question"]
    assert context["conversation_state"] == state
    assert "question_message_id" not in context
    assert result == decision()


def test_a_failed_final_question_gives_no_decision_but_keeps_the_state():
    extractor = ScriptedExtractor({CASE["constraint"]: Extraction([east()])})
    result, state, _ = decide_with_state(
        ScriptedPlanner(fail=True), extractor, CASE, 10
    )

    assert result is None
    assert state["constraints"]["region"]["value"] == "华东"
