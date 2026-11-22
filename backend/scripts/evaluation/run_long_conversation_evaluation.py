"""Does a constraint from the start of a long conversation still reach the plan?

Builds the context with the real functions and asks the real Planner, with and
without standing constraints, so the difference is the feature and nothing else.

record: real gateway behind BudgetGuardGateway, every response saved as a cassette.
replay: cassettes only; a missing recording fails instead of calling a model.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.core.exceptions import StructuredOutputError
from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import RecordReplayGateway, request_key
from app.modules.conversations.service import (
    MAX_CONTEXT_MESSAGES,
    build_conversation_context,
    find_standing_constraints,
)
from app.modules.conversations.state import empty_state
from app.modules.conversations.state_update import (
    apply_update,
    set_subject,
)
from scripts.evaluation.run_planner_route_evaluation import BudgetGuardGateway

FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "evaluation_context"
)
FIXTURE_V1 = FIXTURE_DIR / "long_conversations_v1.json"
FIXTURE = FIXTURE_DIR / "long_conversations_v2.json"
FILLER_QUESTION = "顺便问一下，这个系统的报告在哪里看？"
FILLER_ANSWER = "报告可以在任务详情页查看，也可以导出。"


# A "recent" constraint has this many unrelated turns after it: inside the
# conversation service's window of 8 messages, but not in its last 4.
RECENT_TURNS_AFTER = 2


class ResumingGateway(RecordReplayGateway):
    """Record mode that reads a request already on disk instead of paying for it
    again, so a run stopped by the budget guard can be finished."""

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        path = self._path(request_key(prompt, system_prompt, json_mode=json_mode))
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        return super().chat(prompt, system_prompt, json_mode=json_mode)


def build_messages(
    case: dict, filler_turns: int, filler_answer: str = FILLER_ANSWER
) -> list[SimpleNamespace]:
    """Constraint first (or, if "recent", near the end), then unrelated turns;
    an override sits in the recent window.

    A case may set its own "filler_turns" and may have no "constraint".
    Each of its "inserts" is a user/assistant pair placed after the
    "after_pair"-th pair of that layout (0: before everything), counted before
    any insert is placed; inserts at the same place keep their listed order.
    """
    filler_turns = case.get("filler_turns", filler_turns)
    filler = (("user", FILLER_QUESTION), ("assistant", filler_answer))
    constraint = (
        [(("user", case["constraint"]), ("assistant", "好的，已记下。"))]
        if case.get("constraint")
        else []
    )
    if case.get("constraint_position") == "recent":
        pairs = [filler] * filler_turns + constraint + [filler] * RECENT_TURNS_AFTER
    else:
        pairs = constraint + [filler] * filler_turns
    inserts = case.get("inserts", [])
    placed = []
    for position in range(len(pairs) + 1):
        placed += [
            (("user", insert["user"]), ("assistant", insert["assistant"]))
            for insert in inserts
            if insert["after_pair"] == position
        ]
        if position < len(pairs):
            placed.append(pairs[position])
    contents = [message for pair in placed for message in pair]
    if case.get("override"):
        contents += [("user", case["override"]), ("assistant", "好的。")]
    return [
        SimpleNamespace(id=index, role=role, content=content)
        for index, (role, content) in enumerate(contents, start=1)
    ]


def context_for(
    case: dict,
    filler_turns: int,
    *,
    with_constraints: bool,
    filler_answer: str = FILLER_ANSWER,
) -> dict:
    messages = build_messages(case, filler_turns, filler_answer)
    context = build_conversation_context(messages)
    older = messages[:-MAX_CONTEXT_MESSAGES]
    constraints = find_standing_constraints(older) if with_constraints else []
    if constraints:
        context["standing_constraints"] = constraints
    return context


def score_case(case: dict, decision) -> dict:
    scope = decision.evaluation_scope
    text = " ".join(
        [
            decision.resolved_question or "",
            json.dumps(scope.model_dump(), ensure_ascii=False) if scope else "",
        ]
    )
    required = case.get("must_contain") or []
    # Several standing constraints: one word from every group must be there.
    groups = case.get("must_contain_all") or []
    forbidden = [word for word in case.get("must_not_contain", []) if word in text]
    if decision.action != "analyze":
        passed = bool(case.get("allow_non_analyze")) and not forbidden
    else:
        passed = (
            (not required or any(word in text for word in required))
            and all(any(word in text for word in group) for group in groups)
            and not forbidden
        )
    return {
        "case_id": case["case_id"],
        "split": case["split"],
        "action": decision.action,
        "resolved_question": decision.resolved_question,
        "passed": passed,
    }


# (question, conversation_context) -> PlannerDecision; a function so tests can
# script the Planner without a gateway.
Planner = Callable[[str, dict], Any]
# The Planner gave no valid plan after its retries: the task would fail.
PLANNER_ERROR = "planner_error"


def state_context(
    history: list[SimpleNamespace], state: dict, question_message_id: int
) -> dict:
    """What the Planner sees with a conversation state (C6): recent history as
    the conversation service selects it, the state, and the question's id."""
    context = build_conversation_context(history)
    context["conversation_state"] = state
    context["question_message_id"] = question_message_id
    return context


def simulate_state(
    planner: Planner, messages: list[SimpleNamespace]
) -> tuple[dict, list[dict]]:
    """Replay the conversation turn by turn and return (state, rejected items).

    Starting from ``empty_state()``, every user message that is not the
    filler question is asked as the current question, with the messages
    before it as history and the state so far (``state_context``).  Its
    ``state_update`` goes through ``apply_update`` with the messages up to and
    including that one; each rejected item is logged with ``message_id``.  If
    the Planner chose ``analyze`` with an ``evaluation_scope``, that scope
    becomes the subject (``set_subject``).
    """
    state = empty_state()
    rejected: list[dict] = []
    for position, message in enumerate(messages):
        if message.role != "user" or message.content == FILLER_QUESTION:
            continue
        try:
            decision = planner(
                message.content, state_context(messages[:position], state, message.id)
            )
        except StructuredOutputError:
            # As in the service: a turn whose plan failed changes no state.
            rejected.append(
                {"message_id": message.id, "index": None, "reason": PLANNER_ERROR}
            )
            continue
        state, dropped = apply_update(
            state, decision.state_update, messages[: position + 1]
        )
        rejected += [{"message_id": message.id, **item} for item in dropped]
        scope = decision.evaluation_scope
        if decision.action == "analyze" and scope is not None:
            state = set_subject(state, scope.entities, scope.period)
    return state, rejected


def decide_with_state(
    planner: Planner, case: dict, filler_turns: int, filler_answer: str = FILLER_ANSWER
) -> tuple[Any, dict, list[dict]]:
    """The final question after the simulated turns; its id follows the last one.

    The decision is None when the Planner could not produce a valid plan."""
    messages = build_messages(case, filler_turns, filler_answer)
    state, rejected = simulate_state(planner, messages)
    try:
        decision = planner(
            case["question"], state_context(messages, state, len(messages) + 1)
        )
    except StructuredOutputError:
        decision = None
    return decision, state, rejected


def evaluate_with_state(gateway: ModelGateway, fixture: dict) -> dict:
    from app.modules.analysis.planner.planning import PlanningService

    def planner(question: str, context: dict):
        service = PlanningService(gateway=gateway, sleeper=lambda _seconds: None)
        return service.decide(question, conversation_context=context)

    rows = []
    for case in fixture["cases"]:
        decision, state, rejected = decide_with_state(
            planner,
            case,
            fixture["filler_turns"],
            fixture.get("filler_answer", FILLER_ANSWER),
        )
        scored = (
            score_case(case, decision)
            if decision is not None
            else {
                "case_id": case["case_id"],
                "split": case["split"],
                "action": PLANNER_ERROR,
                "resolved_question": None,
                "passed": False,
            }
        )
        rows.append(
            {
                **scored,
                "constraints": state["constraints"],
                "rejected": rejected,
            }
        )
    return {
        "passed": sum(r["passed"] for r in rows),
        "cases": len(rows),
        "failed": [r["case_id"] for r in rows if not r["passed"]],
        "rejected_items": sum(len(r["rejected"]) for r in rows),
        "rows": rows,
    }


def evaluate(gateway: ModelGateway, fixture: dict, *, with_constraints: bool) -> dict:
    from app.modules.analysis.planner.planning import PlanningService

    rows = []
    for case in fixture["cases"]:
        service = PlanningService(gateway=gateway, sleeper=lambda _seconds: None)
        decision = service.decide(
            case["question"],
            conversation_context=context_for(
                case,
                fixture["filler_turns"],
                with_constraints=with_constraints,
                filler_answer=fixture.get("filler_answer", FILLER_ANSWER),
            ),
        )
        rows.append(score_case(case, decision))
    return {
        "passed": sum(r["passed"] for r in rows),
        "cases": len(rows),
        "failed": [r["case_id"] for r in rows if not r["passed"]],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("record", "replay"), required=True)
    parser.add_argument("--cassette-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument(
        "--resume", action="store_true", help="record: reuse cassettes on disk"
    )
    parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.03"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument(
        "--arms",
        default="standing,none",
        help="comma list of standing (regex constraints), none, state (C6)",
    )
    args = parser.parse_args()
    arms = set(args.arms.split(","))
    if not arms <= {"standing", "none", "state"}:
        parser.error(f"unknown arm in {args.arms}")

    guard: BudgetGuardGateway | None = None
    if args.mode == "replay":
        gateway: ModelGateway = RecordReplayGateway(args.cassette_dir, mode="replay")
    else:
        from app.core.gateway.factory import get_model_gateway

        guard = BudgetGuardGateway(
            get_model_gateway(), max_calls=args.max_calls, max_cost=args.max_cost
        )
        recorder = ResumingGateway if args.resume else RecordReplayGateway
        gateway = recorder(args.cassette_dir, mode="record", inner=guard)

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    report: dict = {}
    if "standing" in arms:
        report["with_standing_constraints"] = evaluate(
            gateway, fixture, with_constraints=True
        )
    if "none" in arms:
        report["without_standing_constraints"] = evaluate(
            gateway, fixture, with_constraints=False
        )
    if "state" in arms:
        report["with_conversation_state"] = evaluate_with_state(gateway, fixture)
    report["model_calls"] = guard.calls if guard else 0
    report["estimated_cost_usd"] = str(guard.estimated_cost) if guard else "0"
    if args.report:
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
