"""Does a constraint from the start of a long conversation still reach the plan?

Builds the context with the real functions and asks the real Planner, with and
without standing constraints, so the difference is the feature and nothing else.

record: real gateway behind BudgetGuardGateway, every response saved as a cassette.
replay: cassettes only; a missing recording fails instead of calling a model.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import RecordReplayGateway
from app.modules.conversations.service import (
    MAX_CONTEXT_MESSAGES,
    build_conversation_context,
    find_standing_constraints,
)
from scripts.evaluation.run_planner_route_evaluation import BudgetGuardGateway

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "evaluation_context"
    / "long_conversations_v1.json"
)
FILLER_QUESTION = "顺便问一下，这个系统的报告在哪里看？"
FILLER_ANSWER = "报告可以在任务详情页查看，也可以导出。"


def build_messages(case: dict, filler_turns: int) -> list[SimpleNamespace]:
    """Constraint first, then unrelated turns; an override sits in the recent window."""
    contents = [("user", case["constraint"]), ("assistant", "好的，已记下。")]
    for _ in range(filler_turns):
        contents += [("user", FILLER_QUESTION), ("assistant", FILLER_ANSWER)]
    if case.get("override"):
        contents += [("user", case["override"]), ("assistant", "好的。")]
    return [
        SimpleNamespace(id=index, role=role, content=content)
        for index, (role, content) in enumerate(contents, start=1)
    ]


def context_for(case: dict, filler_turns: int, *, with_constraints: bool) -> dict:
    messages = build_messages(case, filler_turns)
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
    forbidden = [word for word in case.get("must_not_contain", []) if word in text]
    if decision.action != "analyze":
        passed = bool(case.get("allow_non_analyze")) and not forbidden
    else:
        passed = (not required or any(word in text for word in required)) and (
            not forbidden
        )
    return {
        "case_id": case["case_id"],
        "split": case["split"],
        "action": decision.action,
        "resolved_question": decision.resolved_question,
        "passed": passed,
    }


def evaluate(gateway: ModelGateway, fixture: dict, *, with_constraints: bool) -> dict:
    from app.modules.analysis.planner.planning import PlanningService

    rows = []
    for case in fixture["cases"]:
        service = PlanningService(gateway=gateway, sleeper=lambda _seconds: None)
        decision = service.decide(
            case["question"],
            conversation_context=context_for(
                case, fixture["filler_turns"], with_constraints=with_constraints
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
    parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.03"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    guard: BudgetGuardGateway | None = None
    if args.mode == "replay":
        gateway: ModelGateway = RecordReplayGateway(args.cassette_dir, mode="replay")
    else:
        from app.core.gateway.factory import get_model_gateway

        guard = BudgetGuardGateway(
            get_model_gateway(), max_calls=40, max_cost=args.max_cost
        )
        gateway = RecordReplayGateway(args.cassette_dir, mode="record", inner=guard)

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    report = {
        "with_standing_constraints": evaluate(gateway, fixture, with_constraints=True),
        "without_standing_constraints": evaluate(
            gateway, fixture, with_constraints=False
        ),
        "model_calls": guard.calls if guard else 0,
        "estimated_cost_usd": str(guard.estimated_cost) if guard else "0",
    }
    if args.report:
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
