"""C9c: the long-conversation evaluation catches the summary up before planning."""

import copy

from app.modules.analysis.planner.planner_decision import PlannerDecision
from app.modules.conversations.state_extractor import Extraction
from app.modules.conversations.summarizer import MODEL_ERROR, Summarization
from app.modules.conversations.summary_update import UNKNOWN_MESSAGE
from scripts.evaluation.run_long_conversation_evaluation import (
    build_messages,
    compare_by_case,
    decide_with_state,
    simulate_summary,
    summary_for,
)

# The constraint pair and ten filler pairs: 22 messages, the window holds 15-22.
CASE = {
    "constraint": "后面都只看华东区。",
    "filler_turns": 10,
    "question": "2025年8月已交付订单销售额是多少？",
}
WINDOW_START = 15
# Two filler pairs: six messages, all inside the window.
SHORT = {**CASE, "filler_turns": 2}


def messages():
    return build_messages(CASE, 10)


class ScriptedSummarizer:
    """Answers each call with ``answer(call number, batch)``; keeps what it saw."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls: list[tuple[dict, list[int]]] = []

    def __call__(self, summary: dict, batch: list) -> Summarization:
        self.calls.append((copy.deepcopy(summary), [m.id for m in batch]))
        return self.answer(len(self.calls), batch)


def cite_first(_call: int, batch: list) -> Summarization:
    """One item per batch, citing its first message."""
    first = batch[0].id
    return Summarization([{"text": f"要点{first}", "source_message_ids": [first]}])


def test_the_summary_catches_up_twelve_messages_at_a_time():
    summarizer = ScriptedSummarizer(cite_first)
    summary, rejected = simulate_summary(summarizer, messages())

    assert [ids for _, ids in summarizer.calls] == [list(range(1, 13)), [13, 14]]
    # The second batch is merged into what the first one left.
    assert summarizer.calls[1][0]["items"] == [
        {"text": "要点1", "source_message_ids": [1]}
    ]
    assert summary["items"] == [{"text": "要点13", "source_message_ids": [13]}]
    assert (summary["covered_through"], summary["incremental_count"]) == (14, 2)
    assert rejected == []


def test_a_conversation_inside_the_window_calls_nothing():
    summarizer = ScriptedSummarizer(cite_first)
    summary, rejected = simulate_summary(summarizer, build_messages(SHORT, 2))

    assert summarizer.calls == []
    assert (summary["items"], rejected) == ([], [])


def test_an_item_citing_the_window_is_rejected_and_logged():
    # Each batch is checked against the messages up to its end, as the job
    # does, so a message in the window is not among them.
    def cite_window(_call, batch):
        return Summarization(
            [{"text": "窗口里的话", "source_message_ids": [WINDOW_START]}]
        )

    summary, rejected = simulate_summary(ScriptedSummarizer(cite_window), messages())

    assert summary["items"] == []
    assert rejected == [
        {"message_id": 12, "index": 0, "reason": UNKNOWN_MESSAGE},
        {"message_id": 14, "index": 0, "reason": UNKNOWN_MESSAGE},
    ]


def test_a_failed_call_ends_the_catch_up_and_is_logged():
    summarizer = ScriptedSummarizer(
        lambda _call, _batch: Summarization(error=MODEL_ERROR)
    )
    summary, rejected = simulate_summary(summarizer, messages())

    assert len(summarizer.calls) == 1
    assert summary["covered_through"] == 0
    assert rejected == [{"message_id": None, "index": None, "reason": MODEL_ERROR}]


def test_the_planner_gets_only_what_sits_before_its_history():
    history_summary, _ = summary_for(ScriptedSummarizer(cite_first), messages())
    assert history_summary == ["要点13"]
    assert summary_for(ScriptedSummarizer(cite_first), build_messages(SHORT, 2)) == (
        None,
        [],
    )


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


def test_the_planner_is_given_the_summary_with_the_state():
    seen: list[dict] = []

    def planner(question, context, **kwargs):
        seen.append(kwargs)
        return decision()

    def extractor(state, history, current):
        return Extraction()

    decide_with_state(planner, extractor, CASE, 10, history_summary=["要点1"])
    decide_with_state(planner, extractor, CASE, 10)

    assert seen == [{"history_summary": ["要点1"]}, {}]


def test_cases_are_compared_one_by_one():
    def arm(*passed):
        return {"rows": [{"case_id": c, "passed": p} for c, p in passed]}

    base = arm(("a", True), ("b", False), ("c", True))
    other = arm(("a", True), ("b", True), ("c", False))

    assert compare_by_case(base, other) == {"gained": ["b"], "lost": ["c"]}
