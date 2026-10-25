import hashlib
from pathlib import Path

from app.modules.evaluation.business import evaluate_run
from app.modules.evaluation.business_schemas import (
    EvaluationFixture,
    EvaluationObservation,
)
from app.modules.evaluation.thresholds import (
    EvaluationThresholdContract,
    evaluate_threshold_contract,
)


def test_threshold_contract_rejects_unknown_cost_and_fixture_drift() -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
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
        cost="0.010000",
        cost_status="passed",
    )
    _, metrics = evaluate_run([case], [observation])
    contract = EvaluationThresholdContract(
        schema_version="p0-evaluation-thresholds-v1",
        fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
        required_split="development",
        expected_case_count=1,
        max_total_settled_cost_usd="0.30",
        require_hard_gate_passed=False,
    )

    assert (
        evaluate_threshold_contract(
            contract,
            fixture_bytes=fixture_bytes,
            cases=[case],
            observations=[observation],
            metrics=metrics,
        )
        == []
    )
    assert evaluate_threshold_contract(
        contract,
        fixture_bytes=b"different",
        cases=[case],
        observations=[observation],
        metrics=metrics.model_copy(
            update={"settled_cost": None, "cost_status": "unknown"}
        ),
    ) == ["fixture_sha256", "settled_cost"]


def test_threshold_contract_rejects_candidate_relative_regression() -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
    case = fixture.cases[0]
    observation = EvaluationObservation(
        case_id=case.case_id,
        source="persisted_task",
        actual_outcome="completed",
        model_calls=1,
        tokens=100,
        report_persisted=True,
        numeric_checks_passed=True,
        numeric_check_status="passed",
        deterministic_validation_passed=True,
        deterministic_validation_status="passed",
        citation_validation_status="passed",
        security_check_status="passed",
        duration_ms=121,
        cost="0.012001",
        cost_status="passed",
    )
    _, metrics = evaluate_run([case], [observation])
    contract = EvaluationThresholdContract(
        schema_version="p0-evaluation-thresholds-v1",
        fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
        required_split="development",
        expected_case_count=1,
        max_total_settled_cost_usd="0.30",
        require_hard_gate_passed=False,
        baseline_run_sha256="a" * 64,
        max_duration_p95_multiplier="1.20",
        max_cost_per_trusted_success_multiplier="1.20",
    )
    baseline_metrics = metrics.model_copy(
        update={"duration_p95_ms": 100, "settled_cost": "0.010000"}
    )

    assert evaluate_threshold_contract(
        contract,
        fixture_bytes=fixture_bytes,
        cases=[case],
        observations=[observation],
        metrics=metrics,
        baseline_metrics=baseline_metrics,
        baseline_run_sha256="a" * 64,
    ) == [
        "duration_p95_multiplier",
        "cost_per_trusted_success_multiplier",
    ]
    assert evaluate_threshold_contract(
        contract,
        fixture_bytes=fixture_bytes,
        cases=[case],
        observations=[observation],
        metrics=metrics.model_copy(update={"duration_p95_ms": 120}),
        baseline_metrics=baseline_metrics,
        baseline_run_sha256="a" * 64,
    ) == ["cost_per_trusted_success_multiplier"]

    assert evaluate_threshold_contract(
        contract.model_copy(update={"max_cost_per_trusted_success_multiplier": None}),
        fixture_bytes=fixture_bytes,
        cases=[case],
        observations=[observation],
        metrics=metrics.model_copy(update={"success_count": 1, "duration_p95_ms": 100}),
        baseline_metrics=baseline_metrics.model_copy(update={"success_count": 1}),
        baseline_run_sha256="a" * 64,
    ) == ["cost_per_trusted_success_multiplier"]


def test_v2_threshold_compares_machine_execution_time_not_review_wait() -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
    case = fixture.cases[0]
    observation = EvaluationObservation(
        case_id=case.case_id,
        source="persisted_task",
        actual_outcome="completed",
        model_calls=1,
        tokens=100,
        report_persisted=True,
        numeric_checks_passed=True,
        numeric_check_status="passed",
        deterministic_validation_passed=True,
        deterministic_validation_status="passed",
        citation_validation_status="passed",
        security_check_status="passed",
        duration_ms=70000,
        machine_execution_duration_ms=121,
        human_review_wait_ms=60000,
        cost="0.010000",
        cost_status="passed",
    )
    _, metrics = evaluate_run([case], [observation])
    metrics = metrics.model_copy(update={"success_count": 1})
    contract = EvaluationThresholdContract(
        schema_version="p0-evaluation-thresholds-v2",
        fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
        required_split="development",
        expected_case_count=1,
        max_total_settled_cost_usd="0.30",
        require_hard_gate_passed=False,
        baseline_run_sha256="b" * 64,
        max_machine_execution_duration_p95_multiplier="1.20",
        max_cost_per_trusted_success_multiplier="1.20",
    )
    baseline_metrics = metrics.model_copy(
        update={
            "duration_p95_ms": 100,
            "machine_execution_duration_p95_ms": 100,
            "human_review_wait_p95_ms": 0,
        }
    )

    assert evaluate_threshold_contract(
        contract,
        fixture_bytes=fixture_bytes,
        cases=[case],
        observations=[observation],
        metrics=metrics,
        baseline_metrics=baseline_metrics,
        baseline_run_sha256="b" * 64,
    ) == ["machine_execution_duration_p95_multiplier"]
    assert (
        evaluate_threshold_contract(
            contract,
            fixture_bytes=fixture_bytes,
            cases=[case],
            observations=[observation],
            metrics=metrics.model_copy(
                update={"machine_execution_duration_p95_ms": 120}
            ),
            baseline_metrics=baseline_metrics,
            baseline_run_sha256="b" * 64,
        )
        == []
    )


def test_machine_duration_baseline_contract_is_development_only() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_hybrid_revenue_causality_development_v1.json"
    )
    contract_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "p0_development_single_machine_duration_baseline_thresholds_v2.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
    contract = EvaluationThresholdContract.model_validate_json(
        contract_path.read_bytes()
    )

    assert [case.split for case in fixture.cases] == ["development"]
    assert contract.schema_version == "p0-evaluation-thresholds-v2"
    assert contract.fixture_sha256 == hashlib.sha256(fixture_bytes).hexdigest()
    assert contract.max_machine_execution_duration_p95_multiplier is None
    assert contract.max_cost_per_trusted_success_multiplier is None


def test_machine_duration_candidate_contract_locks_the_r55_baseline() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_hybrid_revenue_causality_development_v1.json"
    )
    contract_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "p0_development_single_machine_duration_candidate_thresholds_v2.json"
    )
    contract = EvaluationThresholdContract.model_validate_json(
        contract_path.read_bytes()
    )

    assert (
        contract.fixture_sha256 == hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    )
    assert contract.baseline_run_sha256 == (
        "dbb6efc142e7f97a9b40558748830263dea7abb0bc03bb0907c0075ec7cca600"
    )
    assert str(contract.max_machine_execution_duration_p95_multiplier) == "1.20"
    assert str(contract.max_cost_per_trusted_success_multiplier) == "1.20"


def test_threshold_contract_rejects_case_model_call_and_token_limits() -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
    case = fixture.cases[0]
    observation = EvaluationObservation(
        case_id=case.case_id,
        source="persisted_task",
        actual_outcome="failed",
        model_calls=case.max_model_calls + 1,
        tokens=case.max_tokens + 1,
        report_persisted=False,
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        duration_ms=0,
        cost="0.010000",
        cost_status="passed",
    )
    _, metrics = evaluate_run([case], [observation])
    contract = EvaluationThresholdContract(
        schema_version="p0-evaluation-thresholds-v1",
        fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(),
        required_split="development",
        expected_case_count=1,
        max_total_settled_cost_usd="0.30",
        require_hard_gate_passed=False,
    )

    assert evaluate_threshold_contract(
        contract,
        fixture_bytes=fixture_bytes,
        cases=[case],
        observations=[observation],
        metrics=metrics,
    ) == ["max_model_calls", "max_tokens"]


def test_repair_measurement_contract_is_development_only_and_not_a_promotion_gate() -> (
    None
):
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_east_sales_comparison_repair_development_v1.json"
    )
    contract_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "p0_data_east_sales_comparison_repair_development_thresholds_v1.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
    contract = EvaluationThresholdContract.model_validate_json(
        contract_path.read_bytes()
    )

    assert [case.split for case in fixture.cases] == ["development"]
    assert fixture.cases[0].max_model_calls == 5
    assert fixture.cases[0].max_tokens == 10000
    assert contract.fixture_sha256 == hashlib.sha256(fixture_bytes).hexdigest()
    assert contract.require_hard_gate_passed is False
    assert str(contract.max_total_settled_cost_usd) == "0.15"


def test_semantic_projection_repair_contract_is_development_only() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_east_sales_comparison_repair_development_v2.json"
    )
    contract_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "p0_data_east_sales_comparison_repair_development_thresholds_v2.json"
    )
    fixture_bytes = fixture_path.read_bytes()
    fixture = EvaluationFixture.model_validate_json(fixture_bytes)
    contract = EvaluationThresholdContract.model_validate_json(
        contract_path.read_bytes()
    )

    assert [case.split for case in fixture.cases] == ["development"]
    assert fixture.cases[0].expected_semantic_result_fingerprint is not None
    assert contract.fixture_sha256 == hashlib.sha256(fixture_bytes).hexdigest()
    assert contract.require_hard_gate_passed is False
