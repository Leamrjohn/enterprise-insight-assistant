"""Component evaluation: fixed question and scope -> Data Agent -> result check.

Runs the real SQL generation, semantic review, validation and read-only
execution against the acme demo database, then compares the returned rows with
a hand-written reference query.  No task, tool runtime or Planner is involved.

record: real gateway behind BudgetGuardGateway, every response saved as a cassette.
replay: cassettes only; a missing recording fails instead of calling a model.
check:  no model; run reference queries and cross-check them against history.

Needs ACME_DEMO_DATABASE_PASSWORD; the host defaults to the compose host port.
"""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

from app.core.gateway.base import ModelGateway
from app.core.gateway.replay import RecordReplayGateway
from app.modules.evaluation.sql_results import score_result, summarize
from scripts.evaluation.run_planner_route_evaluation import (
    BudgetGuardExceeded,
    BudgetGuardGateway,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = BACKEND_ROOT / "tests" / "fixtures" / "evaluation_sql" / "sql_results_v1.json"
# Fingerprint prefixes recorded by earlier end-to-end runs.
EAST_MONTH_FINGERPRINT = "7c587b5f"
EAST_COMPARISON_FINGERPRINT = "ab3c4bf4"


def demo_source():
    from app.modules.organizations.models import BusinessDataSource

    return BusinessDataSource(
        dialect="postgresql",
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        connection_config={
            "host": os.environ.get("BUSINESS_SECURITY_TEST_HOST", "localhost"),
            "port": int(os.environ.get("BUSINESS_SECURITY_TEST_ACME_PORT", "5435")),
            "database": "acme_business",
            "user": "acme_readonly",
            "schema": "public",
        },
    )


def load_catalog(source):
    from app.modules.analysis.catalog.schema_discovery import discover_postgres_schema
    from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog

    return SnapshotCatalog.from_snapshot(discover_postgres_schema(source)[0])


def reference_rows(case: dict, *, source, catalog) -> list[tuple]:
    from app.modules.analysis.data.sql_executor import execute_readonly_sql

    _, rows = execute_readonly_sql(
        case["reference_sql"],
        set(catalog.tables),
        catalog=catalog,
        data_source=source,
    )
    return rows


def cross_check_references(cases: list[dict], *, source, catalog) -> dict:
    """Compare two references with answers recorded before they were written."""
    from app.modules.evaluation.result_fingerprint import (
        revenue_month_comparison_fingerprint_from_data_result,
    )

    by_id = {case["case_id"]: case for case in cases}
    pair = reference_rows(
        by_id["revenue-east-month-comparison"], source=source, catalog=catalog
    )
    pair_print = revenue_month_comparison_fingerprint_from_data_result(
        {
            "status": "ready",
            "evidence": [
                {
                    "columns": ["month", "revenue"],
                    "rows": [[month, str(value)] for month, value in pair],
                    "metric_assessment": {
                        "status": "supported",
                        "metric_definition_ref": "revenue/v1",
                    },
                }
            ],
        },
        period="2025-08 compared_to 2025-07",
    )
    return {
        "east_comparison_matches_history": (pair_print or {})
        .get("value", "")
        .startswith(EAST_COMPARISON_FINGERPRINT),
    }


def evaluate_case(case: dict, *, gateway: ModelGateway, source, catalog) -> dict:
    from app.modules.analysis.data.data_agent import DataAgent
    from app.modules.analysis.data.sql_generation import SQLGenerationService
    from app.modules.reporting.semantic_review_service import SemanticReviewService

    agent = DataAgent(
        sql_generator=SQLGenerationService(gateway=gateway, catalog=catalog),
        data_source=source,
        snapshot_catalog=catalog,
        semantic_reviewer=SemanticReviewService(
            gateway=gateway, sleeper=lambda _seconds: None
        ),
    )
    output = agent.run(
        _agent_input(
            question=case["question"],
            user_id=0,
            context={
                "semantic_review_enabled": True,
                "plan": {
                    "evaluation_scope": {
                        "entities": case["entities"],
                        "period": case["period"],
                    }
                },
            },
        )
    )
    evidence = output.evidence[0] if output.evidence else {}
    expect = case.get("expect", "rows")
    verdict = score_result(
        expect=expect,
        agent_success=output.success,
        actual_rows=evidence.get("rows"),
        reference_rows=(
            reference_rows(case, source=source, catalog=catalog)
            if expect == "rows"
            else None
        ),
        ordered=case.get("ordered", False),
        compare_text=case.get("compare_text", False),
        error_code=output.error_code,
    )
    return {
        "case_id": case["case_id"],
        "split": case["split"],
        "verdict": verdict,
        "error_code": output.error_code,
        "attempts": output.attempts,
        "sql": evidence.get("sql"),
        "rows": evidence.get("rows"),
    }


def _agent_input(**kwargs):
    from app.modules.analysis.data.data_agent import AgentInput

    return AgentInput(**kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("record", "replay", "check"), required=True)
    parser.add_argument("--cassette-dir", type=Path)
    parser.add_argument("--max-calls", type=int, default=80)
    parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.10"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    source = demo_source()
    catalog = load_catalog(source)
    if args.mode == "check":
        report: dict = {
            "reference_rows": {
                case["case_id"]: len(
                    reference_rows(case, source=source, catalog=catalog)
                )
                for case in cases
                if "reference_sql" in case
            },
            **cross_check_references(cases, source=source, catalog=catalog),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    guard: BudgetGuardGateway | None = None
    if args.mode == "replay":
        gateway: ModelGateway = RecordReplayGateway(args.cassette_dir, mode="replay")
    else:
        from app.core.gateway.factory import get_model_gateway

        guard = BudgetGuardGateway(
            get_model_gateway(), max_calls=args.max_calls, max_cost=args.max_cost
        )
        gateway = RecordReplayGateway(args.cassette_dir, mode="record", inner=guard)

    results, stopped = [], None
    for case in cases:
        try:
            results.append(
                evaluate_case(case, gateway=gateway, source=source, catalog=catalog)
            )
        except BudgetGuardExceeded as exc:
            stopped = str(exc)
            break
    report = {
        "mode": args.mode,
        "stopped_by_budget_guard": stopped,
        "model_calls": guard.calls if guard else 0,
        "estimated_cost_usd": str(guard.estimated_cost) if guard else "0",
        **summarize(results),
        "results": results,
    }
    if args.report:
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    summary = {key: value for key, value in report.items() if key != "results"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
