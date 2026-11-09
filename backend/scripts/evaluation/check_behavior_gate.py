"""E10a: fail CI when an offline or replayed evaluation falls below its baseline.

Each evaluation script already writes a JSON report; this reads one report, turns
it into a few named counts and compares each with behavior_gate_baseline.json:
``min`` counts (cases answered right) may not drop, ``max`` counts (errors, wrong
numbers let through) may not rise.  Nothing here calls a model.

    python scripts/evaluation/check_behavior_gate.py planner_route planner.json
    python scripts/evaluation/check_behavior_gate.py plan_rules rules.json
    python scripts/evaluation/check_behavior_gate.py sql_results sql.json
    python scripts/evaluation/check_behavior_gate.py retrieval retrieval.json

A deliberate change that moves a count (a re-recording, a new rule) updates the
baseline file in the same commit, with the reason in its ``notes``.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = (
    BACKEND_ROOT
    / "tests"
    / "fixtures"
    / "evaluation_gate"
    / "behavior_gate_baseline.json"
)

# SQL verdicts that hand a user a number that is not the reference answer.
SQL_RELEASED_WRONG = frozenset(
    {
        "answered_should_reject",
        "value_for_no_data",
        "false_empty",
        "wrong_row_count",
        "wrong_values",
        "same_values_other_shape",
    }
)
SQL_PASSING = frozenset({"correct", "correct_extra_columns", "correct_no_data"})


def planner_route_counts(report: dict) -> dict[str, float]:
    results = report["results"]
    return {
        "cases": len(results),
        "correct": sum(r["correct"] for r in results),
        "errors": sum(r["actual"] == "error" for r in results),
    }


def plan_rules_counts(report: dict) -> dict[str, float]:
    counts: dict[str, float] = {}
    for rule, score in sorted(report["rules"].items()):
        counts[f"{rule}.right"] = score["right"]
        counts[f"{rule}.wrong"] = len(score["wrong"])
    comparison = report["comparison"]
    counts["with_rules.correct"] = comparison["with_rules"]["correct"]
    counts["conflicts"] = len(comparison["conflicts"])
    return counts


def sql_results_counts(report: dict) -> dict[str, float]:
    verdicts = [r["verdict"] for r in report["results"]]
    return {
        "cases": len(verdicts),
        "passed": sum(v in SQL_PASSING for v in verdicts),
        "released_wrong": sum(v in SQL_RELEASED_WRONG for v in verdicts),
    }


def retrieval_counts(report: dict) -> dict[str, float]:
    """Counts for the one policy the gate runs (the main chain's setting)."""
    if len(report["policies"]) != 1:
        raise ValueError("the gate scores exactly one retrieval policy")
    policy = report["policies"][0]

    def hits(block: dict, metric: str) -> int:
        return round(block["overall"][metric] * block["overall"]["cases"])

    traps = policy["version_traps"]["overall"]
    in_prompt = policy["answer_in_prompt"]
    return {
        "cases": policy["final"]["overall"]["cases"],
        "final.hit_at_1": hits(policy["final"], "hit_at_1"),
        "final.hit_at_3": hits(policy["final"], "hit_at_3"),
        "candidates.hit_at_10": hits(policy["candidates"], "hit_at_10"),
        "answer_in_prompt": round(in_prompt["rate"] * in_prompt["cases"]),
        "traps.right_version_first": traps["right_version_first"],
        "traps.wrong_version_above_right": traps["wrong_version_above_right"],
    }


EXTRACTORS: dict[str, Callable[[dict], dict[str, float]]] = {
    "planner_route": planner_route_counts,
    "plan_rules": plan_rules_counts,
    "sql_results": sql_results_counts,
    "retrieval": retrieval_counts,
}


def compare(counts: dict[str, float], baseline: dict) -> list[str]:
    """Return one line per regression; an empty list means the gate passes."""
    problems = []
    for name, floor in baseline.get("min", {}).items():
        if name not in counts:
            problems.append(f"{name}: missing from the report")
        elif counts[name] < floor:
            problems.append(f"{name}: {counts[name]} < baseline {floor}")
    for name, ceiling in baseline.get("max", {}).items():
        if name not in counts:
            problems.append(f"{name}: missing from the report")
        elif counts[name] > ceiling:
            problems.append(f"{name}: {counts[name]} > baseline {ceiling}")
    for name, expected in baseline.get("equal", {}).items():
        if counts.get(name) != expected:
            problems.append(f"{name}: {counts.get(name)} != baseline {expected}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=sorted(EXTRACTORS))
    parser.add_argument("report", type=Path)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        counts = EXTRACTORS[args.component](report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"refused: cannot read {args.report}: {type(exc).__name__}: {exc}")
        return 2
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    expected = baseline["components"][args.component]
    problems = compare(counts, expected)
    if (
        "policy_id" in expected
        and report["policies"][0]["policy_id"] != expected["policy_id"]
    ):
        problems.append(
            f"policy {report['policies'][0]['policy_id']} has no baseline "
            f"(baseline is for {expected['policy_id']})"
        )
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    for problem in problems:
        print(problem)
    print(f"{args.component}: {'regressed' if problems else 'passed'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
