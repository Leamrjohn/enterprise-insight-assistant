"""Score each shadow plan rule against the routing labels (B2d). No model calls.

A rule is right on a case when its suggestion is one of the labelled acceptable
decisions. Cases no rule matches are the Planner's alone: that is coverage, not error.
"""

from __future__ import annotations

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
    matching_rules,
)

LABELS = BACKEND_ROOT / "tests/fixtures/evaluation_routing/planner_routes_v1.json"
# Rules read only whether a period exists, so the date does not change any result.
TODAY = date(2026, 11, 7)


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
        "rules": per_rule,
    }


def main() -> None:
    label_doc = json.loads(LABELS.read_text(encoding="utf-8"))
    cases = [case for case in label_doc["cases"] if case["included"]]
    report = {"label_version": label_doc["version"], **score_rules(cases)}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
