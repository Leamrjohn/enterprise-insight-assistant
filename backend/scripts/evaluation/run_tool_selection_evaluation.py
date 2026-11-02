"""Tool-selection baseline: which tools would the fixed Planner route call?

record: real gateway behind BudgetGuardGateway, every response saved as a cassette.
replay: cassettes only; a missing recording fails instead of calling a model.

Later strategies (model-chosen tools) are scored on the same cases so the fixed
route stays the number to beat.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import RecordReplayGateway
from app.modules.evaluation.tool_selection import (
    score_tool_case,
    summarize_tool_cases,
    tools_for_decision,
)
from scripts.evaluation.run_planner_route_evaluation import (
    BudgetGuardExceeded,
    BudgetGuardGateway,
)

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
ROUTE_LABELS = FIXTURES / "evaluation_routing" / "planner_routes_v1.json"
EXTRA_CASES = FIXTURES / "evaluation_tools" / "tool_selection_extra_v1.json"


def load_cases(
    route_labels: Path = ROUTE_LABELS, extra_cases: Path = EXTRA_CASES
) -> list[dict]:
    """Confirmed routing labels mapped to tool sets, plus the tool-specific cases."""
    cases = []
    for case in json.loads(route_labels.read_text(encoding="utf-8"))["cases"]:
        if not case["included"]:
            continue
        acceptable = {tools_for_decision(item) for item in case["acceptable"]}
        if None in acceptable:
            raise ValueError(f"unknown route label in {case['case_id']}")
        cases.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "question": case["question"],
                "acceptable": sorted(acceptable, key=sorted),
                "forbidden": frozenset(),
            }
        )
    for case in json.loads(extra_cases.read_text(encoding="utf-8"))["cases"]:
        cases.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "question": case["question"],
                "acceptable": [frozenset(item) for item in case["acceptable"]],
                "forbidden": frozenset(case.get("forbidden", [])),
            }
        )
    return cases


def evaluate(gateway: ModelGateway, cases: list[dict]) -> list[dict]:
    from app.modules.analysis.planner.planning import PlanningService

    rows = []
    for case in cases:
        service = PlanningService(gateway=gateway, sleeper=lambda _seconds: None)
        try:
            decision = service.decide(case["question"])
            label = f"{decision.action}/{decision.route}"
        except BudgetGuardExceeded:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad case must not hide the rest
            label = "error"
            print(f"{case['case_id']}: {type(exc).__name__}", file=sys.stderr)
        rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "decision": label,
                **score_tool_case(
                    called=tools_for_decision(label),
                    acceptable=case["acceptable"],
                    forbidden=case["forbidden"],
                ),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("record", "replay"), required=True)
    parser.add_argument("--cassette-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=80)
    parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.06"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    guard: BudgetGuardGateway | None = None
    if args.mode == "replay":
        gateway: ModelGateway = RecordReplayGateway(args.cassette_dir, mode="replay")
    else:
        from app.core.gateway.factory import get_model_gateway

        guard = BudgetGuardGateway(
            get_model_gateway(), max_calls=args.max_calls, max_cost=args.max_cost
        )
        gateway = RecordReplayGateway(args.cassette_dir, mode="record", inner=guard)

    stopped, rows = None, []
    try:
        rows = evaluate(gateway, load_cases())
    except BudgetGuardExceeded as exc:
        stopped = str(exc)
    report = {
        "strategy": "fixed_planner_route",
        "mode": args.mode,
        "stopped_by_budget_guard": stopped,
        "model_calls": guard.calls if guard else 0,
        "estimated_cost_usd": str(guard.estimated_cost) if guard else "0",
        **summarize_tool_cases(rows),
    }
    if args.report:
        args.report.write_text(
            json.dumps({**report, "results": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
