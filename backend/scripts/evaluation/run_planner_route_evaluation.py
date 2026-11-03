"""Component evaluation of Planner routing with a hard spend guard and replay.

record: real gateway behind BudgetGuardGateway, every response saved as a cassette.
replay: cassettes only; a missing recording fails instead of calling a model.
local:  the free simulator, for checking the harness itself.

Model governance does not meter calls outside a task scope, so this script
enforces its own call and estimated-cost ceilings before each call.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import RecordReplayGateway

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = BACKEND_ROOT / "tests" / "fixtures" / "evaluation"
# deepseek-v4.1-flash-peak-2026-10-10 cache-miss prices, per 1k tokens.
PROMPT_PRICE_PER_1K = Decimal("0.0003")
COMPLETION_PRICE_PER_1K = Decimal("0.0012")
RESERVED_COMPLETION_TOKENS = 512


class BudgetGuardExceeded(RuntimeError):
    pass


class BudgetGuardGateway(ModelGateway):
    """Refuse a call whose worst-case estimate would cross the call or cost ceiling."""

    def __init__(self, inner: ModelGateway, *, max_calls: int, max_cost: Decimal):
        self._inner = inner
        self.max_calls = max_calls
        self.max_cost = max_cost
        self.calls = 0
        self.estimated_cost = Decimal(0)

    def _cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        return (
            Decimal(prompt_tokens) * PROMPT_PRICE_PER_1K
            + Decimal(completion_tokens) * COMPLETION_PRICE_PER_1K
        ) / 1000

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        prompt_tokens = self._inner.count_tokens((system_prompt or "") + prompt)
        worst_case = self._cost(prompt_tokens, RESERVED_COMPLETION_TOKENS)
        if self.calls >= self.max_calls:
            raise BudgetGuardExceeded(f"call ceiling {self.max_calls} reached")
        if self.estimated_cost + worst_case > self.max_cost:
            raise BudgetGuardExceeded(
                f"next call could exceed ${self.max_cost} "
                f"(spent ~${self.estimated_cost:.6f})"
            )
        self.calls += 1
        response = self._inner.chat(prompt, system_prompt, json_mode=json_mode)
        self.estimated_cost += self._cost(
            prompt_tokens, self._inner.count_tokens(response)
        )
        return response

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        request = json.dumps([messages, tools], ensure_ascii=False)
        prompt_tokens = self._inner.count_tokens(request)
        worst_case = self._cost(prompt_tokens, RESERVED_COMPLETION_TOKENS)
        if self.calls >= self.max_calls:
            raise BudgetGuardExceeded(f"call ceiling {self.max_calls} reached")
        if self.estimated_cost + worst_case > self.max_cost:
            raise BudgetGuardExceeded(
                f"next call could exceed ${self.max_cost} "
                f"(spent ~${self.estimated_cost:.6f})"
            )
        self.calls += 1
        response = self._inner.chat_with_tools(messages, tools, tool_choice=tool_choice)
        written = (response.text or "") + "".join(
            call.arguments for call in response.tool_calls
        )
        self.estimated_cost += self._cost(
            prompt_tokens, self._inner.count_tokens(written)
        )
        return response

    def count_tokens(self, text: str) -> int:
        return self._inner.count_tokens(text)


def load_route_cases(fixture_root: Path = FIXTURE_ROOT) -> list[dict]:
    """Unique questions whose fixture states the expected planner decision."""
    cases: dict[str, dict] = {}
    for path in sorted(fixture_root.glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8")).get("cases", []):
            if case.get("expected_route"):
                expected = ("analyze", case["expected_route"])
            elif case.get("expected_outcome") == "needs_clarification":
                expected = ("needs_clarification", None)
            else:
                continue
            previous = cases.get(case["question"])
            if previous is not None and previous["expected"] != expected:
                raise ValueError(f"conflicting labels for {case['case_id']}")
            if previous is None or case["split"] == "heldout":
                cases[case["question"]] = {
                    "case_id": case["case_id"],
                    "split": case["split"],
                    "question": case["question"],
                    "expected": expected,
                }
    return list(cases.values())


def score(results: list[dict]) -> dict:
    def accuracy(rows: list[dict]) -> float | None:
        return sum(r["correct"] for r in rows) / len(rows) if rows else None

    return {
        "cases": len(results),
        "accuracy": accuracy(results),
        "by_split": {
            split: accuracy([r for r in results if r["split"] == split])
            for split in sorted({r["split"] for r in results})
        },
        "confusion": dict(
            Counter(
                f"{r['expected']} -> {r['actual']}" for r in results if not r["correct"]
            )
        ),
        "errors": sum(r["actual"] == "error" for r in results),
    }


def score_with_routing_labels(results: list[dict], label_doc: dict) -> dict:
    """Score against a routing-specific label set; excluded cases are not counted."""
    labels = {case["case_id"]: case for case in label_doc["cases"]}
    missing = [r["case_id"] for r in results if r["case_id"] not in labels]
    if missing:
        raise ValueError(f"routing labels missing for {missing}")
    included = [r for r in results if labels[r["case_id"]]["included"]]
    rows = [
        {**r, "correct": r["actual"] in labels[r["case_id"]]["acceptable"]}
        for r in included
    ]
    return {
        "label_version": label_doc["version"],
        "label_status": label_doc["status"],
        "excluded": len(results) - len(included),
        **score(rows),
        "still_wrong": [r["case_id"] for r in rows if not r["correct"]],
    }


def evaluate(gateway: ModelGateway, cases: list[dict]) -> list[dict]:
    from app.modules.analysis.planner.planning import PlanningService

    results = []
    for case in cases:
        service = PlanningService(gateway=gateway, sleeper=lambda _seconds: None)
        try:
            decision = service.decide(case["question"])
            actual = f"{decision.action}/{decision.route}"
        except BudgetGuardExceeded:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad case must not hide the rest
            actual = "error"
            print(f"{case['case_id']}: {type(exc).__name__}", file=sys.stderr)
        expected = f"{case['expected'][0]}/{case['expected'][1]}"
        results.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "expected": expected,
                "actual": actual,
                "correct": actual == expected,
                "model_attempts": service.model_attempts,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("record", "replay", "local"), required=True)
    parser.add_argument("--cassette-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=80)
    parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.08"))
    parser.add_argument(
        "--labels", type=Path, help="optional routing-specific label set"
    )
    args = parser.parse_args()

    guard: BudgetGuardGateway | None = None
    if args.mode == "replay":
        gateway: ModelGateway = RecordReplayGateway(args.cassette_dir, mode="replay")
    else:
        if args.mode == "local":
            from app.core.gateway.local import LocalModelGateway

            inner: ModelGateway = LocalModelGateway()
        else:
            from app.core.gateway.factory import get_model_gateway

            inner = get_model_gateway()
        guard = BudgetGuardGateway(
            inner, max_calls=args.max_calls, max_cost=args.max_cost
        )
        gateway = RecordReplayGateway(args.cassette_dir, mode="record", inner=guard)

    cases = load_route_cases()
    stopped = None
    try:
        results = evaluate(gateway, cases)
    except BudgetGuardExceeded as exc:
        stopped, results = str(exc), []
    report = {
        "mode": args.mode,
        "stopped_by_budget_guard": stopped,
        "calls": guard.calls if guard else 0,
        "estimated_cost_usd": str(guard.estimated_cost) if guard else "0",
        **score(results),
        "results": results,
    }
    if args.labels is not None and results:
        label_doc = json.loads(args.labels.read_text(encoding="utf-8"))
        report["routing_labels"] = score_with_routing_labels(results, label_doc)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
