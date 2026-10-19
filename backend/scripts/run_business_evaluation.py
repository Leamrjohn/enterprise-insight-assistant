"""Render a versioned evaluation artifact from real Worker observations.

This script deliberately does not invoke an Agent.  A future E2E adapter must
first normalize a persisted task into ``EvaluationObservation``; keeping that
boundary explicit prevents test fixtures from being mistaken for live results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.db.session import SessionLocal
from app.modules.evaluation.business import evaluate_run
from app.modules.evaluation.business_schemas import (
    EvaluationFixture,
    EvaluationObservation,
    EvaluationRun,
)
from app.modules.evaluation.observation import (
    observation_from_duplicate_delivery,
    observation_from_execution_fence,
    observation_from_persisted_task,
    observation_from_request_rejection,
    observation_from_runtime_tool_rejection,
    observation_from_sql_result_limit,
    observation_from_sql_timeout,
    observation_from_sql_validation_rejection,
)
from app.modules.evaluation.thresholds import (
    EvaluationThresholdContract,
    evaluate_threshold_contract,
)


def _git_revision(workspace: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=workspace, text=True
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unavailable"


def _load_task_map(path: Path) -> dict[str, int]:
    try:
        raw_task_map = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read valid task-map JSON: {path}") from error

    if not isinstance(raw_task_map, dict):
        # backend/scripts/run_business_evaluation.py
        raise TypeError("task-map JSON must be an object of case_id to task_id")

    task_map: dict[str, int] = {}
    for case_id, task_id in raw_task_map.items():
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("task-map case_id must be a non-empty string")
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id <= 0:
            raise ValueError(
                f"task-map task_id for case {case_id!r} must be a positive integer"
            )
        task_map[case_id] = task_id

    if len(set(task_map.values())) != len(task_map):
        raise ValueError("task-map task_id values must be unique")

    return task_map


def _load_threshold_contract(
    path: Path,
) -> tuple[EvaluationThresholdContract, bytes, str]:
    try:
        contract_bytes = path.read_bytes()
        contract = EvaluationThresholdContract.model_validate_json(contract_bytes)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read valid threshold contract: {path}") from error
    return contract, contract_bytes, hashlib.sha256(contract_bytes).hexdigest()


def _load_baseline_run(path: Path) -> tuple[EvaluationRun, str]:
    try:
        baseline_bytes = path.read_bytes()
        baseline_run = EvaluationRun.model_validate_json(baseline_bytes)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read valid baseline run: {path}") from error
    return baseline_run, hashlib.sha256(baseline_bytes).hexdigest()


def _validate_baseline_comparability(
    baseline_run: EvaluationRun,
    *,
    fixture: EvaluationFixture,
    cases: list,
    model_version: str,
) -> None:
    if baseline_run.comparison_label != "baseline":
        raise ValueError("baseline run must have comparison_label=baseline")
    if baseline_run.dataset_version != fixture.dataset_version:
        raise ValueError("baseline run dataset_version must match fixture")
    if baseline_run.model_version != model_version:
        raise ValueError("baseline run model_version must match candidate")
    if baseline_run.parameters.get("case_ids") != [case.case_id for case in cases]:
        raise ValueError("baseline run case_ids must match candidate fixture selection")


def _load_rejection_map(path: Path) -> dict[str, dict[str, int | str]]:
    try:
        raw_map = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read valid rejection-map JSON: {path}") from error
    if not isinstance(raw_map, dict):
        raise TypeError("rejection-map JSON must be an object of case_id to reference")

    rejection_map: dict[str, dict[str, int | str]] = {}
    for case_id, reference in raw_map.items():
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("rejection-map case_id must be a non-empty string")
        if not isinstance(reference, dict):
            raise TypeError("rejection-map entry must be an object")
        company_id = reference.get("company_id")
        request_id = reference.get("request_id")
        if (
            isinstance(company_id, bool)
            or not isinstance(company_id, int)
            or company_id <= 0
        ):
            raise ValueError("rejection-map company_id must be a positive integer")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("rejection-map request_id must be a non-empty string")
        rejection_map[case_id] = {
            "company_id": company_id,
            "request_id": request_id,
        }
    return rejection_map


def _select_cases(
    fixture: EvaluationFixture, requested_case_ids: list[str] | None
) -> list:
    """Select a fixture-ordered explicit subset for a reproducible smoke run."""
    if not requested_case_ids:
        return fixture.cases
    if len(requested_case_ids) != len(set(requested_case_ids)):
        raise ValueError("--case-id values must not contain duplicates")
    requested = set(requested_case_ids)
    fixture_ids = {case.case_id for case in fixture.cases}
    unknown = sorted(requested - fixture_ids)
    if unknown:
        raise ValueError(f"--case-id values are not in the fixture: {unknown}")
    return [case for case in fixture.cases if case.case_id in requested]


def _load_observations_from_run(path: Path, cases: list) -> list[EvaluationObservation]:
    """Replay saved normalized observations after their disposable tenant is removed."""
    try:
        previous_run = EvaluationRun.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read valid evaluation run: {path}") from error
    expected_ids = {case.case_id for case in cases}
    observations_by_id = {
        observation.case_id: observation for observation in previous_run.observations
    }
    if len(observations_by_id) != len(previous_run.observations):
        raise ValueError("evaluation run observations must have unique case IDs")
    missing = sorted(expected_ids - set(observations_by_id))
    unexpected = sorted(set(observations_by_id) - expected_ids)
    if missing or unexpected:
        raise ValueError(
            "evaluation run observations must match fixture cases exactly: "
            f"missing={missing}, unexpected={unexpected}"
        )
    if any(item.source == "simulated" for item in observations_by_id.values()):
        raise ValueError("simulated observations cannot be replayed as real evidence")
    return [observations_by_id[case.case_id] for case in cases]


def _simulated_unavailable_observation(case_id: str) -> EvaluationObservation:
    """Record an unavailable run without manufacturing a Gold-compatible result."""
    return EvaluationObservation(
        case_id=case_id,
        source="simulated",
        actual_outcome="failed",
        model_calls=0,
        tokens=0,
        report_persisted=False,
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        duration_ms=0,
        cost=None,
        cost_status="unknown",
    )


def _render_markdown(run: EvaluationRun) -> str:
    metrics = run.metrics
    trusted_success_rate = (
        f"{metrics.trusted_business_analysis_success_rate:.2%}"
        if metrics.trusted_business_analysis_success_rate is not None
        else "unknown"
    )
    source_counts = run.parameters["observation_sources"]
    source_summary = ", ".join(
        f"{source}={count}" for source, count in sorted(source_counts.items())
    )
    cost_summary = (
        metrics.settled_cost
        if metrics.cost_status == "passed" and metrics.settled_cost is not None
        else "unknown"
    )
    lines = [
        f"# Business evaluation: {run.run_id}",
        "",
        f"- Comparison: `{run.comparison_label}`",
        f"- Git: `{run.git_revision}`",
        f"- Dataset: `{run.dataset_version}`",
        f"- Model: `{run.model_version}`",
        f"- Observation sources: `{source_summary}`",
        f"- Settled model cost: `{cost_summary}` (status: `{metrics.cost_status}`)",
        f"- Trusted business analysis success rate: `{trusted_success_rate}`",
        f"- Hard security gate: `{'passed' if metrics.hard_gate_passed else 'FAILED'}` ({metrics.security_incident_count} incidents)",
        "",
        "| Case | Passed | Violations |",
        "|---|---:|---|",
    ]
    for result in run.results:
        lines.append(
            f"| {result.case_id} | {'yes' if result.passed else 'no'} | {', '.join(result.violations) or '-'} |"
        )
    lines.append("")
    if run.parameters.get("simulation_mode"):
        lines.append(
            "> WARNING: this is a simulated unavailable-run baseline. It does not "
            "prove an Agent, Worker, model, database, or security rejection path."
        )
    else:
        lines.append(
            "This artifact evaluates normalized persisted observations. It does not "
            "by itself prove that an LLM, Redis, Celery Worker, or business database "
            "was invoked."
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--task-map", type=Path)
    parser.add_argument("--rejection-map", type=Path)
    parser.add_argument("--runtime-tool-rejection-map", type=Path)
    parser.add_argument("--sql-validation-rejection-map", type=Path)
    parser.add_argument("--sql-timeout-map", type=Path)
    parser.add_argument("--sql-result-limit-map", type=Path)
    parser.add_argument("--duplicate-delivery-map", type=Path)
    parser.add_argument("--execution-fence-map", type=Path)
    parser.add_argument("--observation-run", type=Path)
    parser.add_argument("--threshold-contract", type=Path)
    parser.add_argument("--baseline-run", type=Path)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--simulate-unavailable", action="store_true")
    parser.add_argument(
        "--comparison", choices=("baseline", "candidate"), required=True
    )
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    args = parser.parse_args()

    if args.simulate_unavailable and any(
        value is not None
        for value in (
            args.task_map,
            args.rejection_map,
            args.runtime_tool_rejection_map,
            args.sql_validation_rejection_map,
            args.sql_timeout_map,
            args.sql_result_limit_map,
            args.duplicate_delivery_map,
            args.execution_fence_map,
            args.observation_run,
        )
    ):
        parser.error(
            "--simulate-unavailable cannot be combined with live or saved observations"
        )
    if args.observation_run is not None and (
        args.task_map is not None
        or args.rejection_map is not None
        or args.runtime_tool_rejection_map is not None
        or args.sql_validation_rejection_map is not None
        or args.sql_timeout_map is not None
        or args.sql_result_limit_map is not None
        or args.duplicate_delivery_map is not None
        or args.execution_fence_map is not None
    ):
        parser.error("--observation-run cannot be combined with task maps")
    if (
        not args.simulate_unavailable
        and args.task_map is None
        and args.rejection_map is None
        and args.runtime_tool_rejection_map is None
        and args.sql_validation_rejection_map is None
        and args.sql_timeout_map is None
        and args.sql_result_limit_map is None
        and args.duplicate_delivery_map is None
        and args.execution_fence_map is None
        and args.observation_run is None
    ):
        parser.error("an observation source is required")

    fixture_bytes = args.fixture.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
    cases = _select_cases(fixture, args.case_ids)
    threshold_contract = None
    threshold_contract_sha256 = None
    if args.threshold_contract is not None:
        (
            threshold_contract,
            _threshold_contract_bytes,
            threshold_contract_sha256,
        ) = _load_threshold_contract(args.threshold_contract)
    baseline_run = None
    baseline_run_sha256 = None
    if args.baseline_run is not None:
        baseline_run, baseline_run_sha256 = _load_baseline_run(args.baseline_run)
        _validate_baseline_comparability(
            baseline_run,
            fixture=fixture,
            cases=cases,
            model_version=args.model_version,
        )
    if threshold_contract is not None and threshold_contract.baseline_run_sha256 is not None and baseline_run is None:
        parser.error("--baseline-run is required by the threshold contract")
    task_map = _load_task_map(args.task_map) if args.task_map else {}
    rejection_map = (
        _load_rejection_map(args.rejection_map) if args.rejection_map else {}
    )
    runtime_tool_rejection_map = (
        _load_task_map(args.runtime_tool_rejection_map)
        if args.runtime_tool_rejection_map
        else {}
    )
    sql_validation_rejection_map = (
        _load_task_map(args.sql_validation_rejection_map)
        if args.sql_validation_rejection_map
        else {}
    )
    sql_timeout_map = _load_task_map(args.sql_timeout_map) if args.sql_timeout_map else {}
    sql_result_limit_map = (
        _load_task_map(args.sql_result_limit_map) if args.sql_result_limit_map else {}
    )
    duplicate_delivery_map = (
        _load_task_map(args.duplicate_delivery_map)
        if args.duplicate_delivery_map
        else {}
    )
    execution_fence_map = (
        _load_task_map(args.execution_fence_map) if args.execution_fence_map else {}
    )
    if args.observation_run is not None:
        observations = _load_observations_from_run(args.observation_run, cases)
    elif args.simulate_unavailable:
        observations = [
            _simulated_unavailable_observation(case.case_id) for case in cases
        ]
    else:
        task_case_ids = {
            case.case_id
            for case in cases
            if case.evaluation_kind in {"analysis", "clarification"}
        }
        rejection_case_ids = {
            case.case_id
            for case in cases
            if case.evaluation_kind == "security_rejection"
        }
        runtime_tool_rejection_case_ids = {
            case.case_id
            for case in cases
            if case.evaluation_kind == "runtime_tool_rejection"
        }
        sql_validation_rejection_case_ids = {
            case.case_id
            for case in cases
            if case.evaluation_kind == "sql_validation_rejection"
        }
        sql_timeout_case_ids = {
            case.case_id for case in cases if case.evaluation_kind == "sql_timeout"
        }
        sql_result_limit_case_ids = {
            case.case_id
            for case in cases
            if case.evaluation_kind == "sql_result_limit"
        }
        duplicate_delivery_case_ids = {
            case.case_id
            for case in cases
            if case.evaluation_kind == "duplicate_delivery"
        }
        execution_fence_case_ids = {
            case.case_id for case in cases if case.evaluation_kind == "execution_fence"
        }
        for label, expected_ids, actual_ids in (
            ("task-map", task_case_ids, set(task_map)),
            ("rejection-map", rejection_case_ids, set(rejection_map)),
            (
                "runtime-tool-rejection-map",
                runtime_tool_rejection_case_ids,
                set(runtime_tool_rejection_map),
            ),
            (
                "sql-validation-rejection-map",
                sql_validation_rejection_case_ids,
                set(sql_validation_rejection_map),
            ),
            ("sql-timeout-map", sql_timeout_case_ids, set(sql_timeout_map)),
            ("sql-result-limit-map", sql_result_limit_case_ids, set(sql_result_limit_map)),
            ("duplicate-delivery-map", duplicate_delivery_case_ids, set(duplicate_delivery_map)),
            ("execution-fence-map", execution_fence_case_ids, set(execution_fence_map)),
        ):
            missing = sorted(expected_ids - actual_ids)
            unexpected = sorted(actual_ids - expected_ids)
            if missing or unexpected:
                raise ValueError(
                    f"{label} must match its fixture cases exactly: "
                    f"missing={missing}, unexpected={unexpected}"
                )
        with SessionLocal() as db:
            observations = [
                (
                    observation_from_request_rejection(
                        db,
                        case_id=case.case_id,
                        company_id=rejection_map[case.case_id]["company_id"],
                        request_id=rejection_map[case.case_id]["request_id"],
                    )
                    if case.evaluation_kind == "security_rejection"
                    else observation_from_runtime_tool_rejection(
                        db,
                        case_id=case.case_id,
                        task_id=runtime_tool_rejection_map[case.case_id],
                    )
                    if case.evaluation_kind == "runtime_tool_rejection"
                    else observation_from_sql_validation_rejection(
                        db,
                        case_id=case.case_id,
                        task_id=sql_validation_rejection_map[case.case_id],
                    )
                    if case.evaluation_kind == "sql_validation_rejection"
                    else observation_from_sql_timeout(
                        db,
                        case_id=case.case_id,
                        task_id=sql_timeout_map[case.case_id],
                    )
                    if case.evaluation_kind == "sql_timeout"
                    else observation_from_sql_result_limit(
                        db,
                        case_id=case.case_id,
                        task_id=sql_result_limit_map[case.case_id],
                    )
                    if case.evaluation_kind == "sql_result_limit"
                    else observation_from_duplicate_delivery(
                        db,
                        case_id=case.case_id,
                        task_id=duplicate_delivery_map[case.case_id],
                    )
                    if case.evaluation_kind == "duplicate_delivery"
                    else observation_from_execution_fence(
                        db,
                        case_id=case.case_id,
                        task_id=execution_fence_map[case.case_id],
                    )
                    if case.evaluation_kind == "execution_fence"
                    else observation_from_persisted_task(
                        db,
                        case_id=case.case_id,
                        task_id=task_map[case.case_id],
                    )
                )
                for case in cases
            ]
    results, metrics = evaluate_run(cases, observations)
    threshold_violations = (
        evaluate_threshold_contract(
            threshold_contract,
            fixture_bytes=fixture_bytes,
            cases=cases,
            observations=observations,
            metrics=metrics,
            baseline_metrics=baseline_run.metrics if baseline_run is not None else None,
            baseline_run_sha256=baseline_run_sha256,
        )
        if threshold_contract is not None
        else []
    )
    now = datetime.now(UTC)
    workspace = Path(__file__).resolve().parents[2]
    environment = json.loads(args.environment.read_text(encoding="utf-8"))
    run = EvaluationRun(
        run_id=f"{args.comparison}-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}",
        started_at=now,
        completed_at=now,
        comparison_label=args.comparison,
        git_revision=_git_revision(workspace),
        dataset_version=fixture.dataset_version,
        model_version=args.model_version,
        environment=environment,
        parameters={
            "fixture": str(args.fixture),
            "case_ids": [case.case_id for case in cases],
            "task_map": task_map,
            "rejection_map": rejection_map,
            "runtime_tool_rejection_map": runtime_tool_rejection_map,
            "sql_validation_rejection_map": sql_validation_rejection_map,
            "sql_timeout_map": sql_timeout_map,
            "sql_result_limit_map": sql_result_limit_map,
            "duplicate_delivery_map": duplicate_delivery_map,
            "execution_fence_map": execution_fence_map,
            "observation_count": len(observations),
            "observation_sources": dict(
                sorted(Counter(item.source for item in observations).items())
            ),
            "observation_run": (
                str(args.observation_run) if args.observation_run is not None else None
            ),
            "simulation_mode": "unavailable" if args.simulate_unavailable else None,
            "threshold_contract": (
                {
                    "path": str(args.threshold_contract),
                    "sha256": threshold_contract_sha256,
                    "violations": threshold_violations,
                    "baseline_run": (
                        {
                            "path": str(args.baseline_run),
                            "sha256": baseline_run_sha256,
                        }
                        if args.baseline_run is not None
                        else None
                    ),
                }
                if threshold_contract is not None
                else None
            ),
        },
        observations=observations,
        results=results,
        metrics=metrics,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "run.json").write_text(
        run.model_dump_json(indent=2), encoding="utf-8"
    )
    (args.output_dir / "report.md").write_text(_render_markdown(run), encoding="utf-8")
    print(args.output_dir)
    if threshold_violations:
        raise SystemExit(
            "evaluation threshold contract failed: "
            + ", ".join(threshold_violations)
        )


if __name__ == "__main__":
    main()
