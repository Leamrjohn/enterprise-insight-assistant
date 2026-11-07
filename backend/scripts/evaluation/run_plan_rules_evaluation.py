"""Score each shadow plan rule against the routing labels (B2d, B2i). No model calls.

A rule is right on a case when its suggestion is one of the labelled acceptable
decisions. Cases no rule matches are the Planner's alone: that is coverage, not error.

With --planner-results (a run_planner_route_evaluation report on the same questions)
it also compares final routes: the Planner alone versus the Planner with rules applied.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.analysis.planner.facts import extract_question_facts
from app.modules.analysis.planner.rules import (
    PLAN_RULES,
    RULES_VERSION,
    arbitrate,
    matching_rules,
    rule_question,
)

LABELS = BACKEND_ROOT / "tests/fixtures/evaluation_routing/planner_routes_v1.json"
HELDOUT = BACKEND_ROOT / "tests/fixtures/evaluation_routing/plan_rules_heldout_v1.json"
# R0: a rule needs at least this many held-out cases it fires on before B2e may enable it.
MIN_SAMPLES = 5
CLARIFY = "needs_clarification/None"
# Rules read only whether a period exists, so the date does not change any result.
TODAY = date(2026, 11, 7)


class LabelSetError(ValueError):
    """The label set or Planner results cannot support a verdict."""


def load_cases(label_doc: dict, *, allow_unfrozen: bool = False) -> list[dict]:
    if label_doc.get("status") != "frozen" and not allow_unfrozen:
        raise LabelSetError(
            f"{label_doc['version']} is {label_doc.get('status')!r}, not frozen"
        )
    cases = [case for case in label_doc["cases"] if case.get("included", True)]
    if not cases:
        raise LabelSetError(f"{label_doc['version']} has no cases to score")
    return cases


def score_rules(cases: list[dict], today: date = TODAY) -> dict:
    per_rule = {
        rule.rule_id: {"hits": 0, "right": 0, "wrong": []} for rule in PLAN_RULES
    }
    unmatched = []
    for case in cases:
        hits = matching_rules(extract_question_facts(case["question"], today))
        if not hits:
            unmatched.append(case["case_id"])
        for rule in hits:
            row = per_rule[rule.rule_id]
            row["hits"] += 1
            if rule.suggests in case["acceptable"]:
                row["right"] += 1
            else:
                row["wrong"].append(case["case_id"])
    return {
        "rules_version": RULES_VERSION,
        "cases": len(cases),
        "unmatched": len(unmatched),
        "unmatched_cases": unmatched,
        "rules": per_rule,
        "min_samples": MIN_SAMPLES,
        "short_of_samples": [
            rule_id for rule_id, row in per_rule.items() if row["hits"] < MIN_SAMPLES
        ],
    }


def planner_decisions(route_report: dict) -> dict[str, str]:
    return {row["case_id"]: row["actual"] for row in route_report["results"]}


def compare_routes(
    cases: list[dict],
    planner: dict[str, str],
    enabled: set[str] | None = None,
    today: date = TODAY,
) -> dict:
    """Final route per case with and without the enabled rules.

    Hits are settled by the B2j table (rules.arbitrate); disagreeing hits are listed.
    A case may carry the Planner's resolved_question for a follow-up turn.
    """
    missing = [case["case_id"] for case in cases if case["case_id"] not in planner]
    if missing:
        raise LabelSetError(f"no Planner result for {missing}")
    modes = {
        mode: {"correct": 0, "wrong_clarifications": 0}
        for mode in ("planner_only", "with_rules")
    }
    changed, conflicts = [], []
    for case in cases:
        question, _source = rule_question(case["question"], case)
        hits = [
            rule
            for rule in matching_rules(extract_question_facts(question, today))
            if enabled is None or rule.rule_id in enabled
        ]
        before = planner[case["case_id"]]
        after = arbitrate(hits) or before
        if len({rule.suggests for rule in hits}) > 1:
            conflicts.append(
                {"case_id": case["case_id"], "rules": [rule.rule_id for rule in hits]}
            )
        for mode, decision in (("planner_only", before), ("with_rules", after)):
            right = decision in case["acceptable"]
            modes[mode]["correct"] += right
            modes[mode]["wrong_clarifications"] += decision == CLARIFY and not right
        if after != before:
            fixed = after in case["acceptable"] and before not in case["acceptable"]
            broke = before in case["acceptable"] and after not in case["acceptable"]
            changed.append(
                {
                    "case_id": case["case_id"],
                    "planner": before,
                    "with_rules": after,
                    "effect": "fixed" if fixed else "broke" if broke else "neutral",
                }
            )
    return {
        "enabled": sorted(enabled) if enabled is not None else "all",
        "cases": len(cases),
        **modes,
        "changed": changed,
        "conflicts": conflicts,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    # Held-out sets: score once and record; tuning a rule on them spends them.
    parser.add_argument("--labels", type=Path, default=HELDOUT)
    parser.add_argument(
        "--allow-unfrozen",
        action="store_true",
        help="development sets only; the result is not evidence for B2e",
    )
    parser.add_argument("--planner-results", type=Path)
    parser.add_argument("--enable", help="comma-separated rule ids; default all")
    args = parser.parse_args(argv)
    label_doc = json.loads(args.labels.read_text(encoding="utf-8"))
    try:
        cases = load_cases(label_doc, allow_unfrozen=args.allow_unfrozen)
        report = {
            "label_version": label_doc["version"],
            "label_status": label_doc.get("status"),
            **score_rules(cases),
        }
        if args.planner_results is not None:
            route_report = json.loads(args.planner_results.read_text(encoding="utf-8"))
            enabled = set(args.enable.split(",")) if args.enable else None
            report["comparison"] = compare_routes(
                cases, planner_decisions(route_report), enabled
            )
    except LabelSetError as exc:
        parser.exit(2, f"refused: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
