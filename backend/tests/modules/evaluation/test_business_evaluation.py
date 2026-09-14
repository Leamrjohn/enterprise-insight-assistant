import json
from pathlib import Path

from app.modules.evaluation.business_schemas import (
    EvaluationCase,
    EvaluationFixture,
    EvaluationObservation,
)
from app.modules.evaluation.business import evaluate_case, evaluate_run


def _case(**overrides) -> EvaluationCase:
    values = {
        "case_id": "sales-decline-east-normal",
        "scenario": "sales_decline_east",
        "complexity": "medium",
        "split": "development",
        "question": "为什么2025年8月华东区销售额下降？",
        "company_scope": "acme-demo",
        "document_scope": ["events/2025-08-east-sales-review.md"],
        "expected_route": "hybrid",
        "expected_entities": ["华东", "CUST-0001"],
        "expected_period": "2025-08 compared_to 2025-07",
        "expected_query_requirements": ["按区域汇总", "下钻客户"],
        "expected_result_fingerprint": {"region": "EAST", "direction": "decrease"},
        "expected_confirmed_facts": ["华东区销售额下降"],
        "expected_supported_claims": ["CUST-0001合同到期后暂停采购"],
        "allowed_chunk_ids": [101],
        "forbidden_claims": ["唯一原因"],
        "expected_outcome": "completed",
        "expected_limitations": [],
        "max_model_calls": 4,
        "max_tokens": 2000,
    }
    values.update(overrides)
    return EvaluationCase.model_validate(values)


def _observation(**overrides) -> EvaluationObservation:
    values = {
        "case_id": "sales-decline-east-normal",
        "actual_route": "hybrid",
        "actual_entities": ["华东", "CUST-0001"],
        "actual_period": "2025-08 compared_to 2025-07",
        "actual_result_fingerprint": {"region": "EAST", "direction": "decrease"},
        "actual_confirmed_facts": ["华东区销售额下降"],
        "actual_supported_claims": ["CUST-0001合同到期后暂停采购"],
        "returned_chunk_ids": [101],
        "returned_document_paths": ["events/2025-08-east-sales-review.md"],
        "actual_outcome": "completed",
        "actual_limitations": [],
        "model_calls": 3,
        "tokens": 1200,
        "report_persisted": True,
        "numeric_checks_passed": True,
        "deterministic_validation_passed": True,
        "security_incidents": [],
        "duration_ms": 600,
    }
    values.update(overrides)
    return EvaluationObservation.model_validate(values)


def test_trusted_success_requires_every_contract_dimension() -> None:
    result = evaluate_case(_case(), _observation())
    assert result.passed
    assert result.violations == []


def test_forbidden_claim_and_security_incident_fail_hard_gate() -> None:
    result = evaluate_case(
        _case(),
        _observation(
            actual_confirmed_facts=["这是唯一原因"],
            security_incidents=["cross_company_document"],
        ),
    )
    assert not result.passed
    assert "forbidden_claim_free" in result.violations
    assert "security_gate_passed" in result.violations


def test_run_rejects_missing_observation_and_reports_p95() -> None:
    case = _case()
    try:
        evaluate_run([case], [])
    except ValueError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("missing observation must be rejected")

    _, metrics = evaluate_run([case], [_observation(duration_ms=900)])
    assert metrics.trusted_business_analysis_success_rate == 1.0
    assert metrics.duration_p95_ms == 900
    assert metrics.hard_gate_passed


def test_sales_decline_fixture_is_versioned_and_has_isolated_heldout_cases() -> None:
    fixture_path = Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    fixture = EvaluationFixture.model_validate(json.loads(fixture_path.read_text(encoding="utf-8")))
    assert len([case for case in fixture.cases if case.split == "development"]) == 5
    assert len([case for case in fixture.cases if case.split == "heldout"]) == 1
