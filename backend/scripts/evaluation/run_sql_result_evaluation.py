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
    """An unsaved acme source bound to an unsaved platform connection (A11b).

    Loopback hosts are refused by the connection policy, so this runs on the
    compose or CI network and reaches the demo database by its service name.
    """
    from app.modules.organizations.connections import new_connection
    from app.modules.organizations.models import BusinessDataSource

    connection = new_connection(
        company_id=0,
        name="evaluation-acme-demo",
        host=os.environ.get("BUSINESS_SECURITY_TEST_HOST", "demo_business_acme"),
        port=int(os.environ.get("BUSINESS_SECURITY_TEST_ACME_PORT", "5432")),
        database="acme_business",
        username="acme_readonly",
        schema_name="public",
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        operator="evaluation",
    )
    return BusinessDataSource(
        company_id=0,
        dialect="postgresql",
        connection_config={},
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        connection=connection,
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


def first_try_passed(attempts: dict) -> bool:
    """Did the first SQL the model wrote get through every gate?"""
    loop = attempts.get("tool_loop")
    if loop is None:
        return attempts.get("model_attempts") == 1 and attempts.get("sql_attempts") == 1
    if "switched_to_fixed" in attempts:
        return False
    sql_calls = [step for step in loop["trace"] if step["tool"] == "run_sql"]
    return bool(sql_calls) and sql_calls[0]["outcome"] != "repairable"


def evaluate_case(
    case: dict, *, gateway: ModelGateway, source, catalog, strategy: str = "fixed"
) -> dict:
    from app.modules.analysis.data.data_agent import DataAgent
    from app.modules.analysis.data.sql_generation import SQLGenerationService
    from app.modules.analysis.data.tool_agent import ToolCallingDataAgent
    from app.modules.reporting.semantic_review_service import SemanticReviewService

    shared = {
        "sql_generator": SQLGenerationService(gateway=gateway, catalog=catalog),
        "data_source": source,
        "snapshot_catalog": catalog,
        "semantic_reviewer": SemanticReviewService(
            gateway=gateway, sleeper=lambda _seconds: None
        ),
    }
    agent = (
        DataAgent(**shared)
        if strategy == "fixed"
        else ToolCallingDataAgent(
            gateway=gateway, seed_schema=strategy == "tools_seeded", **shared
        )
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
        "blocked_sql_check": _check_blocked_sql(
            case, evidence, source=source, catalog=catalog
        ),
        "error_code": output.error_code,
        "attempts": output.attempts,
        "first_try_passed": first_try_passed(output.attempts or {}),
        "sql": evidence.get("sql"),
        "rows": evidence.get("rows"),
    }


def _check_blocked_sql(case: dict, evidence: dict, *, source, catalog) -> str | None:
    """Diagnostic only: would SQL that a gate stopped have given the right answer?

    It tells "the model wrote wrong SQL" from "a gate refused right SQL" and never
    changes the verdict.  The SQL still goes through validation and read-only
    execution.
    """
    from app.modules.analysis.data.sql_executor import execute_readonly_sql

    sql = evidence.get("sql")
    if not sql or evidence.get("rows") is not None or "reference_sql" not in case:
        return None
    try:
        _, rows = execute_readonly_sql(
            sql, set(catalog.tables), catalog=catalog, data_source=source
        )
    except Exception as exc:  # noqa: BLE001 - the error type is the finding here
        return "execution_error_" + type(exc).__name__
    return score_result(
        expect="rows",
        agent_success=True,
        actual_rows=rows,
        reference_rows=reference_rows(case, source=source, catalog=catalog),
        ordered=case.get("ordered", False),
        compare_text=case.get("compare_text", False),
    )


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
    parser.add_argument(
        "--strategy",
        choices=("fixed", "tools_seeded", "tools_on_demand"),
        default="fixed",
    )
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
                evaluate_case(
                    case,
                    gateway=gateway,
                    source=source,
                    catalog=catalog,
                    strategy=args.strategy,
                )
            )
        except BudgetGuardExceeded as exc:
            stopped = str(exc)
            break
    report = {
        "mode": args.mode,
        "stopped_by_budget_guard": stopped,
        "model_calls": guard.calls if guard else 0,
        "estimated_cost_usd": str(guard.estimated_cost) if guard else "0",
        "strategy": args.strategy,
        "first_try_passed": sum(r["first_try_passed"] for r in results),
        "switched_to_fixed": [
            r["case_id"]
            for r in results
            if "switched_to_fixed" in (r["attempts"] or {})
        ],
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
