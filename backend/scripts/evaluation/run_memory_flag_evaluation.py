"""Does the evidence review flag memories it should, and leave the others alone?

record: real gateway behind BudgetGuardGateway, every response saved as a cassette.
replay: cassettes only; a missing recording fails instead of calling a model.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import RecordReplayGateway
from scripts.evaluation.run_planner_route_evaluation import BudgetGuardGateway

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "evaluation_memory"
    / "memory_flags_v1.json"
)
MEMORY_ID = 1


def summarize(rows: list[dict]) -> dict:
    should = [r for r in rows if r["should_flag"]]
    should_not = [r for r in rows if not r["should_flag"]]
    caught = [r for r in should if r["flagged"]]
    return {
        "cases": len(rows),
        "flag_recall": len(caught) / len(should) if should else None,
        "missed": [r["case_id"] for r in should if not r["flagged"]],
        "false_flags": [r["case_id"] for r in should_not if r["flagged"]],
        "meets_target": bool(should)
        and len(caught) / len(should) >= 0.8
        and not any(r["flagged"] for r in should_not),
    }


def evaluate(gateway: ModelGateway, cases: list[dict]) -> list[dict]:
    from app.modules.reporting.semantic_review_service import SemanticReviewService

    service = SemanticReviewService(gateway=gateway, sleeper=lambda _seconds: None)
    rows = []
    for case in cases:
        review = service.review_evidence(
            question=case["question"],
            plan={"action": "analyze", "route": "data_only"},
            data_result={
                "status": "ready",
                "evidence": [
                    {
                        "purpose": case["question"],
                        "columns": case["columns"],
                        "rows": case["rows"],
                    }
                ],
            },
            knowledge_result={},
            report={"status": "completed", "executive_summary": "见数据结果"},
            memories_used=[
                {
                    "memory_id": MEMORY_ID,
                    "memory_type": "validated_report_facts",
                    "content": {"confirmed_facts": [{"statement": case["memory"]}]},
                }
            ],
        )
        rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "should_flag": case["should_flag"],
                "flagged": any(
                    item.memory_id == MEMORY_ID for item in review.contradicted_memories
                ),
                "verdict": review.verdict,
                "reasons": [item.reason for item in review.contradicted_memories],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("record", "replay"), required=True)
    parser.add_argument("--cassette-dir", type=Path, required=True)
    parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.02"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    guard: BudgetGuardGateway | None = None
    if args.mode == "replay":
        gateway: ModelGateway = RecordReplayGateway(args.cassette_dir, mode="replay")
    else:
        from app.core.gateway.factory import get_model_gateway

        guard = BudgetGuardGateway(
            get_model_gateway(), max_calls=30, max_cost=args.max_cost
        )
        gateway = RecordReplayGateway(args.cassette_dir, mode="record", inner=guard)

    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    rows = evaluate(gateway, cases)
    report = {
        **summarize(rows),
        "model_calls": guard.calls if guard else 0,
        "estimated_cost_usd": str(guard.estimated_cost) if guard else "0",
        "rows": rows,
    }
    if args.report:
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
