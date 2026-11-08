import hashlib
import json
import sys
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

import pytest
from app.modules.evaluation.business import evaluate_run
from app.modules.evaluation.business_schemas import (
    EvaluationFixture,
    EvaluationObservation,
    EvaluationRun,
)
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.workflow.models import AnalysisTask
from scripts.evaluation import run_business_evaluation as evaluation_cli


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.closed = True


def test_cli_replays_saved_observations_without_opening_database(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    case = fixture.cases[0]
    observation = EvaluationObservation(
        case_id=case.case_id,
        source="persisted_task",
        actual_route="hybrid",
        actual_entities=["华东", "CUST-0001"],
        actual_period="2025-08 compared_to 2025-07",
        actual_result_fingerprint={"region": "EAST", "direction": "decrease"},
        actual_confirmed_facts=["华东区销售额下降"],
        actual_supported_claims=["CUST-0001合同到期后暂停采购"],
        returned_chunk_ids=[101],
        returned_document_paths=["events/2025-08-east-sales-review.md"],
        actual_outcome="completed",
        actual_limitations=[],
        model_calls=3,
        tokens=1200,
        report_persisted=True,
        numeric_checks_passed=True,
        numeric_check_status="passed",
        deterministic_validation_passed=True,
        deterministic_validation_status="passed",
        citation_validation_status="passed",
        security_incidents=[],
        security_check_status="passed",
        duration_ms=600,
        cost="0.030000",
        cost_status="passed",
    )
    results, metrics = evaluate_run([case], [observation])
    source_run_path = tmp_path / "saved-run.json"
    source_run_path.write_text(
        EvaluationRun(
            run_id="saved-run",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            comparison_label="candidate",
            git_revision="saved",
            dataset_version=fixture.dataset_version,
            model_version="saved-model",
            environment={"execution": "saved"},
            parameters={},
            observations=[observation],
            results=results,
            metrics=metrics,
        ).model_dump_json(),
        encoding="utf-8",
    )
    baseline_observation = observation.model_copy(
        update={"duration_ms": 500, "cost": "0.010000"}
    )
    baseline_results, baseline_metrics = evaluate_run([case], [baseline_observation])
    baseline_run_path = tmp_path / "baseline-run.json"
    baseline_run_path.write_text(
        EvaluationRun(
            run_id="baseline-run",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            comparison_label="baseline",
            git_revision="baseline",
            dataset_version=fixture.dataset_version,
            model_version="test-model",
            environment={"execution": "baseline"},
            parameters={"case_ids": [case.case_id]},
            observations=[baseline_observation],
            results=baseline_results,
            metrics=baseline_metrics,
        ).model_dump_json(),
        encoding="utf-8",
    )
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"execution": "replay"}), encoding="utf-8")
    threshold_path = tmp_path / "thresholds.json"
    threshold_path.write_text(
        json.dumps(
            {
                "schema_version": "p0-evaluation-thresholds-v1",
                "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                "required_split": "development",
                "expected_case_count": 1,
                "max_total_settled_cost_usd": "0.020000",
                "max_duration_p95_ms": 600,
                "require_hard_gate_passed": False,
                "baseline_run_sha256": hashlib.sha256(
                    baseline_run_path.read_bytes()
                ).hexdigest(),
                "max_duration_p95_multiplier": "1.20",
                "max_cost_per_trusted_success_multiplier": "1.20",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        evaluation_cli,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("replay must not open database")),
    )
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--case-id",
            case.case_id,
            "--observation-run",
            str(source_run_path),
            "--threshold-contract",
            str(threshold_path),
            "--baseline-run",
            str(baseline_run_path),
            "--comparison",
            "candidate",
            "--model-version",
            "test-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    with pytest.raises(
        SystemExit,
        match="max_total_settled_cost_usd, cost_per_trusted_success_multiplier",
    ):
        evaluation_cli.main()

    run_data = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["observations"][0]["actual_route"] == "hybrid"
    assert run_data["observations"][0]["model_calls"] == 3
    assert run_data["parameters"]["observation_run"] == str(source_run_path)
    assert run_data["parameters"]["threshold_contract"]["violations"] == [
        "max_total_settled_cost_usd",
        "cost_per_trusted_success_multiplier",
    ]
    assert run_data["parameters"]["threshold_contract"]["baseline_run"]["sha256"] == (
        hashlib.sha256(baseline_run_path.read_bytes()).hexdigest()
    )


def test_task_map_rejects_boolean_task_id(tmp_path: Path) -> None:
    task_map_path = tmp_path / "task_map.json"
    task_map_path.write_text(
        json.dumps({"case-a": True}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="positive integer"):
        evaluation_cli._load_task_map(task_map_path)


def test_git_revision_is_explicitly_unavailable_without_git(monkeypatch) -> None:
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(evaluation_cli.subprocess, "check_output", no_git)

    assert evaluation_cli._git_revision(Path("workspace")) == "unavailable"


def test_rejection_map_requires_scoped_request_reference(tmp_path: Path) -> None:
    map_path = tmp_path / "rejection_map.json"
    map_path.write_text(
        json.dumps({"security-case": {"company_id": True, "request_id": "r1"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="company_id"):
        evaluation_cli._load_rejection_map(map_path)


def test_cli_uses_rejection_observation_for_security_case(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_version": "security-cli-test-v1",
                "cases": [
                    {
                        "case_id": "security-case",
                        "evaluation_kind": "security_rejection",
                        "scenario": "cross_company",
                        "complexity": "simple",
                        "split": "development",
                        "question": "deny this",
                        "company_scope": "test-company",
                        "expected_route": None,
                        "expected_entities": ["other-company"],
                        "expected_period": "not_applicable",
                        "expected_query_requirements": ["deny"],
                        "expected_result_fingerprint": {"scenario": "denied"},
                        "expected_outcome": "failed",
                        "max_model_calls": 0,
                        "max_tokens": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rejection_map_path = tmp_path / "rejection_map.json"
    rejection_map_path.write_text(
        json.dumps({"security-case": {"company_id": 7, "request_id": "request-7"}}),
        encoding="utf-8",
    )
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"database": "test"}), encoding="utf-8")
    calls: list[tuple[str, int, str]] = []

    def fake_rejection_adapter(db, *, case_id, company_id, request_id):
        calls.append((case_id, company_id, request_id))
        return EvaluationObservation(
            case_id=case_id,
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
            security_check_status="passed",
            rejection_observed_status="passed",
            no_side_effects_status="passed",
        )

    monkeypatch.setattr(evaluation_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        evaluation_cli, "observation_from_request_rejection", fake_rejection_adapter
    )
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--rejection-map",
            str(rejection_map_path),
            "--comparison",
            "baseline",
            "--model-version",
            "test-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    assert calls == [("security-case", 7, "request-7")]
    run_data = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["results"][0]["passed"]
    assert "Trusted business analysis success rate: `unknown`" in (
        output_dir / "report.md"
    ).read_text(encoding="utf-8")


def test_cli_uses_runtime_tool_rejection_observation(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_version": "runtime-tool-rejection-cli-v1",
                "cases": [
                    {
                        "case_id": "runtime-tool-case",
                        "evaluation_kind": "runtime_tool_rejection",
                        "scenario": "document_scope",
                        "complexity": "simple",
                        "split": "development",
                        "question": "deny out-of-scope document",
                        "company_scope": "test-company",
                        "expected_route": None,
                        "expected_entities": ["document"],
                        "expected_period": "not_applicable",
                        "expected_query_requirements": ["deny"],
                        "expected_result_fingerprint": {"scenario": "denied"},
                        "expected_outcome": "failed",
                        "expected_tool_denial_codes": ["tool_document_scope_denied"],
                        "max_model_calls": 0,
                        "max_tokens": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    task_map_path = tmp_path / "runtime-tool-map.json"
    task_map_path.write_text(json.dumps({"runtime-tool-case": 12}), encoding="utf-8")
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"database": "test"}), encoding="utf-8")
    calls: list[tuple[str, int]] = []

    def fake_adapter(db, *, case_id, task_id):
        calls.append((case_id, task_id))
        return EvaluationObservation(
            case_id=case_id,
            source="runtime_tool_rejection",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
            security_check_status="passed",
            runtime_tool_denial_status="passed",
            tool_execution_prevented_status="passed",
            actual_tool_denial_codes=["tool_document_scope_denied"],
            cost="0.000000",
            cost_status="passed",
        )

    monkeypatch.setattr(evaluation_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        evaluation_cli, "observation_from_runtime_tool_rejection", fake_adapter
    )
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--runtime-tool-rejection-map",
            str(task_map_path),
            "--comparison",
            "candidate",
            "--model-version",
            "no-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    assert calls == [("runtime-tool-case", 12)]
    assert json.loads((output_dir / "run.json").read_text(encoding="utf-8"))["results"][
        0
    ]["passed"]


def test_cli_uses_sql_validation_rejection_observation(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_version": "sql-validation-rejection-cli-v1",
                "cases": [
                    {
                        "case_id": "sql-validation-case",
                        "evaluation_kind": "sql_validation_rejection",
                        "scenario": "schema_injection",
                        "complexity": "simple",
                        "split": "development",
                        "question": "deny evaluation schema",
                        "company_scope": "test-company",
                        "expected_route": None,
                        "expected_entities": ["evaluation.scenario_truth"],
                        "expected_period": "not_applicable",
                        "expected_query_requirements": ["deny"],
                        "expected_result_fingerprint": {"scenario": "denied"},
                        "expected_outcome": "failed",
                        "expected_sql_validation_codes": ["sql_validation_error"],
                        "max_model_calls": 0,
                        "max_tokens": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    task_map_path = tmp_path / "sql-validation-map.json"
    task_map_path.write_text(json.dumps({"sql-validation-case": 13}), encoding="utf-8")
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"database": "test"}), encoding="utf-8")
    calls: list[tuple[str, int]] = []

    def fake_adapter(db, *, case_id, task_id):
        calls.append((case_id, task_id))
        return EvaluationObservation(
            case_id=case_id,
            source="sql_validation_rejection",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
            security_check_status="passed",
            sql_validation_rejection_status="passed",
            business_result_prevented_status="passed",
            actual_sql_validation_codes=["sql_validation_error"],
            cost="0.000000",
            cost_status="passed",
        )

    monkeypatch.setattr(evaluation_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        evaluation_cli, "observation_from_sql_validation_rejection", fake_adapter
    )
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--sql-validation-rejection-map",
            str(task_map_path),
            "--comparison",
            "candidate",
            "--model-version",
            "no-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    assert calls == [("sql-validation-case", 13)]
    assert json.loads((output_dir / "run.json").read_text(encoding="utf-8"))["results"][
        0
    ]["passed"]


def test_cli_uses_sql_timeout_observation(tmp_path: Path, monkeypatch) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_version": "sql-timeout-cli-v1",
                "cases": [
                    {
                        "case_id": "sql-timeout-case",
                        "evaluation_kind": "sql_timeout",
                        "scenario": "statement_timeout",
                        "complexity": "simple",
                        "split": "development",
                        "question": "timeout query",
                        "company_scope": "test-company",
                        "expected_route": None,
                        "expected_entities": ["sales_orders"],
                        "expected_period": "not_applicable",
                        "expected_query_requirements": ["statement timeout"],
                        "expected_result_fingerprint": {"scenario": "timeout"},
                        "expected_outcome": "failed",
                        "expected_sql_timeout_codes": ["sql_statement_timeout"],
                        "max_model_calls": 0,
                        "max_tokens": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    task_map_path = tmp_path / "sql-timeout-map.json"
    task_map_path.write_text(json.dumps({"sql-timeout-case": 14}), encoding="utf-8")
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"database": "test"}), encoding="utf-8")
    calls: list[tuple[str, int]] = []

    def fake_adapter(db, *, case_id, task_id):
        calls.append((case_id, task_id))
        return EvaluationObservation(
            case_id=case_id,
            source="sql_timeout",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
            security_check_status="passed",
            sql_timeout_status="passed",
            sql_timeout_result_prevented_status="passed",
            actual_sql_timeout_codes=["sql_statement_timeout"],
            cost="0.000000",
            cost_status="passed",
        )

    monkeypatch.setattr(evaluation_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(evaluation_cli, "observation_from_sql_timeout", fake_adapter)
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--sql-timeout-map",
            str(task_map_path),
            "--comparison",
            "candidate",
            "--model-version",
            "no-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    assert calls == [("sql-timeout-case", 14)]
    run_data = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["results"][0]["passed"]
    assert run_data["parameters"]["sql_timeout_map"] == {"sql-timeout-case": 14}


def test_cli_uses_duplicate_delivery_observation(tmp_path: Path, monkeypatch) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_version": "duplicate-delivery-cli-v1",
                "cases": [
                    {
                        "case_id": "duplicate-delivery-case",
                        "evaluation_kind": "duplicate_delivery",
                        "scenario": "second_claim_rejected",
                        "complexity": "simple",
                        "split": "development",
                        "question": "duplicate delivery",
                        "company_scope": "test-company",
                        "expected_route": None,
                        "expected_entities": ["task"],
                        "expected_period": "not_applicable",
                        "expected_query_requirements": ["reject second claim"],
                        "expected_result_fingerprint": {"scenario": "duplicate"},
                        "expected_outcome": "completed",
                        "expected_duplicate_delivery_codes": [
                            "execution_already_claimed"
                        ],
                        "max_model_calls": 0,
                        "max_tokens": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    task_map_path = tmp_path / "duplicate-delivery-map.json"
    task_map_path.write_text(
        json.dumps({"duplicate-delivery-case": 14}), encoding="utf-8"
    )
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"database": "test"}), encoding="utf-8")
    calls: list[tuple[str, int]] = []

    def fake_adapter(db, *, case_id, task_id):
        calls.append((case_id, task_id))
        return EvaluationObservation(
            case_id=case_id,
            source="duplicate_delivery",
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
            security_check_status="passed",
            duplicate_delivery_status="passed",
            duplicate_execution_prevented_status="passed",
            actual_duplicate_delivery_codes=["execution_already_claimed"],
            cost="0.000000",
            cost_status="passed",
        )

    monkeypatch.setattr(evaluation_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        evaluation_cli, "observation_from_duplicate_delivery", fake_adapter
    )
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--duplicate-delivery-map",
            str(task_map_path),
            "--comparison",
            "candidate",
            "--model-version",
            "no-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    assert calls == [("duplicate-delivery-case", 14)]
    assert json.loads((output_dir / "run.json").read_text(encoding="utf-8"))["results"][
        0
    ]["passed"]


def test_cli_rejects_incomplete_task_map_before_opening_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    task_map_path = tmp_path / "task_map.json"
    task_map_path.write_text(
        json.dumps(
            {
                "sales-decline-east-normal": 101,
            }
        ),
        encoding="utf-8",
    )

    environment_path = tmp_path / "environment.json"
    environment_path.write_text(
        json.dumps({"database": "test"}),
        encoding="utf-8",
    )

    def fail_if_database_is_opened():
        raise AssertionError("incomplete task-map must not open a database session")

    monkeypatch.setattr(
        evaluation_cli,
        "SessionLocal",
        fail_if_database_is_opened,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--task-map",
            str(task_map_path),
            "--comparison",
            "baseline",
            "--model-version",
            "test-model",
            "--output-dir",
            str(tmp_path / "output"),
            "--environment",
            str(environment_path),
        ],
    )

    with pytest.raises(ValueError, match="missing="):
        evaluation_cli.main()


def test_cli_runs_an_explicit_fixture_subset_in_fixture_order(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    case_id = fixture_data["cases"][0]["case_id"]
    task_map_path = tmp_path / "task_map.json"
    task_map_path.write_text(json.dumps({case_id: 101}), encoding="utf-8")
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"database": "test"}), encoding="utf-8")
    calls: list[tuple[str, int]] = []

    def fake_adapter(db, *, case_id: str, task_id: int) -> EvaluationObservation:
        calls.append((case_id, task_id))
        return EvaluationObservation(
            case_id=case_id,
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
        )

    monkeypatch.setattr(evaluation_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(evaluation_cli, "observation_from_persisted_task", fake_adapter)
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--task-map",
            str(task_map_path),
            "--case-id",
            case_id,
            "--comparison",
            "baseline",
            "--model-version",
            "test-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    assert calls == [(case_id, 101)]
    run_data = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["parameters"]["case_ids"] == [case_id]
    assert run_data["observations"][0]["case_id"] == case_id
    assert run_data["observations"][0]["source"] == "persisted_task"


def test_cli_simulates_an_unavailable_30_case_run_without_opening_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "business_gold_v1.json"
    )
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(
        json.dumps({"execution": "simulated"}), encoding="utf-8"
    )

    def fail_if_database_is_opened():
        raise AssertionError("simulation must not open a database session")

    monkeypatch.setattr(evaluation_cli, "SessionLocal", fail_if_database_is_opened)
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--simulate-unavailable",
            "--comparison",
            "baseline",
            "--model-version",
            "not-invoked",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    run_data = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["metrics"]["cases"] == 30
    assert run_data["metrics"]["success_count"] == 0
    assert run_data["metrics"]["fail_count"] > 0
    assert run_data["metrics"]["unknown_count"] > 0
    assert run_data["parameters"]["observation_sources"] == {"simulated": 30}
    assert run_data["parameters"]["simulation_mode"] == "unavailable"
    assert len(run_data["observations"]) == 30
    assert {item["source"] for item in run_data["observations"]} == {"simulated"}
    assert "simulated unavailable-run baseline" in (output_dir / "report.md").read_text(
        encoding="utf-8"
    )


def test_cli_builds_observations_in_fixture_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, int]] = []

    def fake_adapter(db, *, case_id: str, task_id: int) -> EvaluationObservation:
        calls.append((case_id, task_id))
        return EvaluationObservation(
            case_id=case_id,
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
        )

    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
    case_ids = [case["case_id"] for case in fixture_data["cases"]]

    task_map = {case_id: task_id for task_id, case_id in enumerate(case_ids, start=101)}
    task_map_path = tmp_path / "task_map.json"
    task_map_path.write_text(
        json.dumps(task_map),
        encoding="utf-8",
    )

    environment_path = tmp_path / "environment.json"
    environment_path.write_text(
        json.dumps({"database": "test"}),
        encoding="utf-8",
    )
    fake_session = FakeSession()

    monkeypatch.setattr(
        evaluation_cli,
        "SessionLocal",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        evaluation_cli,
        "observation_from_persisted_task",
        fake_adapter,
    )
    monkeypatch.setattr(
        evaluation_cli,
        "_git_revision",
        lambda workspace: "test-revision",
    )
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--task-map",
            str(task_map_path),
            "--comparison",
            "baseline",
            "--model-version",
            "test-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()
    assert calls == [(case_id, task_map[case_id]) for case_id in case_ids]
    assert fake_session.closed

    run_data = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_data["parameters"]["task_map"] == task_map
    assert (output_dir / "report.md").is_file()


def test_cli_reads_persisted_task_and_preserves_unknown_fields(
    db_session,
    test_user,
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = FinalAnalysisReport(
        status="completed",
        executive_summary="测试报告。",
        confirmed_facts=[
            {
                "fact_id": "test-fact",
                "statement": "测试事实。",
                "data_evidence_ids": ["test-evidence"],
            }
        ],
        hypotheses=[],
        data_evidence=[
            {
                "evidence_id": "test-evidence",
                "purpose": "测试指标",
            }
        ],
        document_citations=[],
    )

    task = AnalysisTask(
        user_id=test_user.id,
        question="测试问题",
        status="completed",
        stage="completed",
        result_data={
            "plan": {"route": "hybrid"},
            "report": report.model_dump(mode="json"),
            "deterministic_validation": {
                "status": "passed",
                "checks": {
                    "numbers_valid": True,
                    "citations_valid": True,
                },
            },
        },
    )
    db_session.add(task)
    db_session.flush()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_version": "cli-persisted-task-test-v1",
                "cases": [
                    {
                        "case_id": "persisted-task-case",
                        "scenario": "cli_persisted_task",
                        "complexity": "simple",
                        "split": "development",
                        "question": "测试问题",
                        "company_scope": "test-company",
                        "document_scope": [],
                        "expected_route": "hybrid",
                        "expected_entities": ["east"],
                        "expected_period": "2025-08",
                        "expected_query_requirements": ["test"],
                        "expected_result_fingerprint": {"metric": "sales"},
                        "expected_outcome": "completed",
                        "max_model_calls": 10,
                        "max_tokens": 1000,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    task_map_path = tmp_path / "task_map.json"
    task_map_path.write_text(
        json.dumps({"persisted-task-case": task.id}),
        encoding="utf-8",
    )

    environment_path = tmp_path / "environment.json"
    environment_path.write_text(
        json.dumps({"database": "agent_platform_test"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        evaluation_cli,
        "SessionLocal",
        lambda: nullcontext(db_session),
    )
    monkeypatch.setattr(
        evaluation_cli,
        "_git_revision",
        lambda workspace: "test-revision",
    )
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--task-map",
            str(task_map_path),
            "--comparison",
            "baseline",
            "--model-version",
            "test-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()
    run_data = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    result = run_data["results"][0]

    assert result["route_correct"] is True
    assert result["hard_gate_status"] == "unknown"
    assert result["violations"] == []
    assert {
        "entity_scope_correct",
        "sql_result_equivalent",
        "security_gate_passed",
    }.issubset(result["unknown_checks"])
    assert result["citation_scope_correct"] is True
    assert run_data["parameters"]["task_map"] == {"persisted-task-case": task.id}
    assert run_data["observations"][0]["actual_route"] == "hybrid"


def test_cli_uses_sql_result_limit_observation(tmp_path: Path, monkeypatch) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_version": "sql-result-limit-cli-v1",
                "cases": [
                    {
                        "case_id": "sql-result-limit-case",
                        "evaluation_kind": "sql_result_limit",
                        "scenario": "oversized_sql_result",
                        "complexity": "simple",
                        "split": "development",
                        "question": "限制 SQL 返回行数。",
                        "company_scope": "test-company",
                        "document_scope": [],
                        "expected_route": None,
                        "expected_entities": ["sales_orders"],
                        "expected_period": "not_applicable",
                        "expected_query_requirements": ["row limit"],
                        "expected_result_fingerprint": {"scenario": "row_limit"},
                        "expected_outcome": "completed",
                        "expected_sql_result_max_rows": 1000,
                        "max_model_calls": 0,
                        "max_tokens": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    task_map_path = tmp_path / "sql_result_limit_map.json"
    task_map_path.write_text(
        json.dumps({"sql-result-limit-case": 12}), encoding="utf-8"
    )
    environment_path = tmp_path / "environment.json"
    environment_path.write_text(json.dumps({"execution": "test"}), encoding="utf-8")
    calls: list[tuple[str, int]] = []

    def fake_adapter(_db, *, case_id: str, task_id: int) -> EvaluationObservation:
        calls.append((case_id, task_id))
        return EvaluationObservation(
            case_id=case_id,
            source="sql_result_limit",
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            numeric_checks_passed=False,
            deterministic_validation_passed=False,
            security_check_status="passed",
            sql_result_limit_status="passed",
            actual_sql_result_row_count=1000,
            cost="0.000000",
            cost_status="passed",
        )

    monkeypatch.setattr(evaluation_cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        evaluation_cli, "observation_from_sql_result_limit", fake_adapter
    )
    monkeypatch.setattr(evaluation_cli, "_git_revision", lambda workspace: "test")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_business_evaluation.py",
            "--fixture",
            str(fixture_path),
            "--sql-result-limit-map",
            str(task_map_path),
            "--comparison",
            "candidate",
            "--model-version",
            "no-model",
            "--output-dir",
            str(output_dir),
            "--environment",
            str(environment_path),
        ],
    )

    evaluation_cli.main()

    assert calls == [("sql-result-limit-case", 12)]
    assert json.loads((output_dir / "run.json").read_text(encoding="utf-8"))["results"][
        0
    ]["passed"]
