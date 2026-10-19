import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from app.modules.evaluation.business import evaluate_case, evaluate_run
from app.modules.evaluation.business_schemas import (
    EvaluationCase,
    EvaluationFixture,
    EvaluationObservation,
)


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
        "numeric_check_status": "passed",
        "deterministic_validation_passed": True,
        "deterministic_validation_status": "passed",
        "citation_validation_status": "passed",
        "security_incidents": [],
        "security_check_status": "passed",
        "duration_ms": 600,
        "cost": "0.030000",
        "cost_status": "passed",
    }
    values.update(overrides)
    return EvaluationObservation.model_validate(values)


def test_trusted_success_requires_every_contract_dimension() -> None:
    result = evaluate_case(_case(), _observation())
    assert result.passed
    assert result.violations == []


def test_uncomparable_result_fingerprint_shapes_are_unknown_not_failed() -> None:
    result = evaluate_case(
        _case(expected_result_fingerprint={"scenario": "sales_decline_east"}),
        _observation(
            actual_result_fingerprint={"algorithm": "sha256", "value": "0" * 64}
        ),
    )

    assert not result.passed
    assert "sql_result_equivalent" not in result.violations
    assert result.unknown_checks == ["sql_result_equivalent"]


def test_comparable_result_fingerprint_hash_mismatch_still_fails() -> None:
    result = evaluate_case(
        _case(
            expected_result_fingerprint={"algorithm": "sha256", "value": "0" * 64}
        ),
        _observation(
            actual_result_fingerprint={"algorithm": "sha256", "value": "1" * 64}
        ),
    )

    assert not result.passed
    assert "sql_result_equivalent" in result.violations


def test_semantic_result_fingerprint_compares_compatible_projections() -> None:
    result = evaluate_case(
        _case(
            expected_semantic_result_fingerprint={
                "algorithm": "sha256",
                "value": "0" * 64,
            }
        ),
        _observation(
            actual_result_fingerprint={"raw": "different-shape"},
            actual_semantic_result_fingerprint={
                "algorithm": "sha256",
                "value": "0" * 64,
            },
        ),
    )

    assert result.passed


def test_data_revenue_development_fixture_has_an_executable_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_revenue_development_v1.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route="data_only",
            actual_entities=["华东"],
            actual_period="2025-08",
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="completed",
            actual_limitations=[],
        ),
    )

    assert result.passed


def test_data_revenue_semantic_projection_fixture_has_an_executable_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_east_sales_comparison_repair_development_v2.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route="data_only",
            actual_entities=["华东"],
            actual_period=case.expected_period,
            actual_result_fingerprint={"different": "raw-shape"},
            actual_semantic_result_fingerprint=case.expected_semantic_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="completed",
            actual_limitations=[],
        ),
    )

    assert result.passed


def test_hybrid_document_terms_are_evaluated_against_frozen_document_evidence() -> None:
    case = _case(
        expected_supported_claims=[],
        expected_limitations=[],
        expected_document_claim_terms=[{"all_of": ["合同", "到期", "暂停采购"]}],
        expected_document_qualification_terms=[{"all_of": ["不能", "唯一原因"]}],
        expected_outcome="partial",
    )

    result = evaluate_case(
        case,
        _observation(
            actual_supported_claims=["CUST-0001合同到期后暂停常规采购。"],
            actual_document_qualifications=["资料不能证明它是华东销售下降的唯一原因。"],
            actual_outcome="partial",
        ),
    )

    assert result.passed


def test_hybrid_revenue_causality_fixture_has_an_executable_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_hybrid_revenue_causality_development_v1.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_entities=case.expected_entities,
            actual_period=case.expected_period,
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_supported_claims=["CUST-0001合同到期后暂停常规采购。"],
            actual_document_qualifications=[
                "不能仅凭同期性断言为华东全部销售下降的唯一原因。"
            ],
            returned_document_paths=case.document_scope,
        ),
    )

    assert result.passed


def test_document_terms_require_a_document_route_and_frozen_scope() -> None:
    with pytest.raises(ValueError, match="knowledge_only or hybrid"):
        _case(
            expected_route="data_only",
            document_scope=[],
            expected_supported_claims=[],
            expected_limitations=[],
            expected_document_claim_terms=[{"all_of": ["合同"]}],
        )
    with pytest.raises(ValueError, match="frozen document scope"):
        _case(
            document_scope=[],
            expected_supported_claims=[],
            expected_limitations=[],
            expected_document_claim_terms=[{"all_of": ["合同"]}],
        )


def test_registered_region_scope_accepts_its_optional_area_suffix() -> None:
    result = evaluate_case(
        _case(expected_entities=["华东"]),
        _observation(actual_entities=["华东区", "CUST-0001"]),
    )

    assert result.passed


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


def test_forbidden_claim_does_not_reject_a_negated_qualification() -> None:
    result = evaluate_case(
        _case(),
        _observation(
            actual_confirmed_facts=[
                (
                    "关于 CUST-0001 合同到期与暂停采购的关系，以及这些资料能否证明其为华东全部"
                    "销售表现的唯一原因，当前可用数据不足以判断，无法给出结论。"
                )
            ],
            actual_supported_claims=[
                (
                    "合同到期与暂停采购可作为对该客户销售归零的有证据解释，竞争报价是背景信号，"
                    "不能仅凭同期性断言为华东全部销售下降的唯一原因。因此，这些资料不足以证明"
                    "CUST-0001合同到期与暂停采购是华东全部销售表现的唯一原因。"
                )
            ],
        ),
    )

    assert result.forbidden_claim_free is True


def test_security_rejection_is_passed_only_with_explicit_denial_evidence() -> None:
    case = _case(
        evaluation_kind="security_rejection",
        expected_outcome="failed",
        max_model_calls=0,
        max_tokens=0,
    )
    passed = evaluate_case(
        case,
        _observation(
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            rejection_observed_status="passed",
            no_side_effects_status="passed",
        ),
    )
    unknown = evaluate_case(
        case,
        _observation(
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
        ),
    )

    assert passed.passed
    assert passed.route_correct is None
    assert passed.no_side_effects is True
    assert unknown.hard_gate_status == "unknown"
    assert {"rejection_observed", "no_side_effects"}.issubset(unknown.unknown_checks)


def test_runtime_tool_rejection_requires_a_denied_persisted_call() -> None:
    case = _case(
        evaluation_kind="runtime_tool_rejection",
        document_scope=[],
        expected_route=None,
        expected_outcome="failed",
        expected_tool_denial_codes=["tool_document_scope_denied"],
        max_model_calls=0,
        max_tokens=0,
    )
    passed = evaluate_case(
        case,
        _observation(
            source="runtime_tool_rejection",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            runtime_tool_denial_status="passed",
            tool_execution_prevented_status="passed",
            actual_tool_denial_codes=["tool_document_scope_denied"],
        ),
    )
    wrong_code = evaluate_case(
        case,
        _observation(
            source="runtime_tool_rejection",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            runtime_tool_denial_status="passed",
            tool_execution_prevented_status="passed",
            actual_tool_denial_codes=["tool_company_scope_denied"],
        ),
    )

    assert passed.passed
    assert passed.runtime_tool_denial_observed
    assert passed.tool_execution_prevented
    assert not wrong_code.passed
    assert "denial_codes_match" in wrong_code.violations


def test_sql_validation_rejection_requires_a_failed_validation_call() -> None:
    case = _case(
        evaluation_kind="sql_validation_rejection",
        document_scope=[],
        expected_route=None,
        expected_outcome="failed",
        expected_sql_validation_codes=["sql_validation_error"],
        max_model_calls=0,
        max_tokens=0,
    )
    passed = evaluate_case(
        case,
        _observation(
            source="sql_validation_rejection",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            sql_validation_rejection_status="passed",
            business_result_prevented_status="passed",
            actual_sql_validation_codes=["sql_validation_error"],
        ),
    )
    wrong_code = evaluate_case(
        case,
        _observation(
            source="sql_validation_rejection",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            sql_validation_rejection_status="passed",
            business_result_prevented_status="passed",
            actual_sql_validation_codes=["business_db_execution_failed"],
        ),
    )

    assert passed.passed
    assert passed.sql_validation_rejection_observed
    assert passed.business_result_prevented
    assert not wrong_code.passed
    assert "sql_validation_codes_match" in wrong_code.violations


def test_sql_timeout_requires_a_persisted_timeout_without_a_business_result() -> None:
    case = _case(
        evaluation_kind="sql_timeout",
        document_scope=[],
        expected_route=None,
        expected_outcome="failed",
        expected_sql_timeout_codes=["sql_statement_timeout"],
        max_model_calls=0,
        max_tokens=0,
    )
    passed = evaluate_case(
        case,
        _observation(
            source="sql_timeout",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            sql_timeout_status="passed",
            sql_timeout_result_prevented_status="passed",
            actual_sql_timeout_codes=["sql_statement_timeout"],
        ),
    )
    wrong_code = evaluate_case(
        case,
        _observation(
            source="sql_timeout",
            actual_outcome="failed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            sql_timeout_status="passed",
            sql_timeout_result_prevented_status="passed",
            actual_sql_timeout_codes=["business_db_execution_failed"],
        ),
    )

    assert passed.passed
    assert passed.sql_timeout_observed
    assert passed.sql_timeout_result_prevented
    assert not wrong_code.passed
    assert "sql_timeout_codes_match" in wrong_code.violations


def test_sql_result_limit_requires_a_persisted_bounded_row_count() -> None:
    case = _case(
        evaluation_kind="sql_result_limit",
        document_scope=[],
        expected_route=None,
        expected_outcome="completed",
        expected_sql_result_max_rows=1000,
        max_model_calls=0,
        max_tokens=0,
    )

    result = evaluate_case(
        case,
        _observation(
            source="sql_result_limit",
            actual_route=None,
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            sql_result_limit_status="passed",
            actual_sql_result_row_count=1000,
        ),
    )

    assert result.passed
    assert result.sql_result_limit_observed


def test_duplicate_delivery_requires_rejected_second_claim_and_one_execution() -> None:
    case = _case(
        evaluation_kind="duplicate_delivery",
        document_scope=[],
        expected_route=None,
        expected_outcome="completed",
        expected_duplicate_delivery_codes=["execution_already_claimed"],
        max_model_calls=0,
        max_tokens=0,
    )
    passed = evaluate_case(
        case,
        _observation(
            source="duplicate_delivery",
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            duplicate_delivery_status="passed",
            duplicate_execution_prevented_status="passed",
            actual_duplicate_delivery_codes=["execution_already_claimed"],
        ),
    )
    missing_rejection = evaluate_case(
        case,
        _observation(
            source="duplicate_delivery",
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            duplicate_delivery_status="failed",
            duplicate_execution_prevented_status="passed",
        ),
    )

    assert passed.passed
    assert passed.duplicate_delivery_observed
    assert passed.duplicate_execution_prevented
    assert not missing_rejection.passed
    assert "duplicate_delivery" in missing_rejection.violations


def test_execution_fence_requires_cancelled_state_and_persisted_rejection() -> None:
    case = _case(
        evaluation_kind="execution_fence",
        document_scope=[],
        expected_route=None,
        expected_outcome="cancelled",
        expected_execution_fence_codes=["execution_fence_lost"],
        expected_execution_fence_state="cancelled_without_result",
        max_model_calls=0,
        max_tokens=0,
    )
    passed = evaluate_case(
        case,
        _observation(
            source="execution_fence",
            actual_route=None,
            actual_outcome="cancelled",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            execution_fence_status="passed",
            late_execution_write_prevented_status="passed",
            actual_execution_fence_codes=["execution_fence_lost"],
            actual_execution_fence_state="cancelled_without_result",
        ),
    )
    missing_event = evaluate_case(
        case,
        _observation(
            source="execution_fence",
            actual_route=None,
            actual_outcome="cancelled",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            execution_fence_status="passed",
            late_execution_write_prevented_status="failed",
        ),
    )

    assert passed.passed
    assert not missing_event.passed
    assert "late_execution_write_prevented" in missing_event.violations


def test_execution_fence_requires_the_expected_preserved_replacement_state() -> None:
    case = _case(
        evaluation_kind="execution_fence",
        document_scope=[],
        expected_route=None,
        expected_outcome="completed",
        expected_execution_fence_codes=["execution_fence_lost"],
        expected_execution_fence_state="replacement_result_preserved",
        max_model_calls=0,
        max_tokens=0,
    )
    result = evaluate_case(
        case,
        _observation(
            source="execution_fence",
            actual_route=None,
            actual_outcome="completed",
            model_calls=0,
            tokens=0,
            report_persisted=False,
            execution_fence_status="passed",
            late_execution_write_prevented_status="passed",
            actual_execution_fence_codes=["execution_fence_lost"],
            actual_execution_fence_state="replacement_result_preserved",
        ),
    )

    assert result.passed


def test_clarification_terminal_requires_exact_slots_and_no_side_effects() -> None:
    case = _case(
        evaluation_kind="clarification",
        document_scope=[],
        expected_route=None,
        expected_outcome="needs_clarification",
        expected_clarification_missing_fields=["time_range"],
    )
    passed = evaluate_case(
        case,
        _observation(
            actual_route=None,
            actual_outcome="needs_clarification",
            actual_clarification_missing_fields=["time_range"],
            report_persisted=False,
            no_side_effects_status="passed",
            security_check_status="passed",
        ),
    )
    wrong_slot = evaluate_case(
        case,
        _observation(
            actual_route=None,
            actual_outcome="needs_clarification",
            actual_clarification_missing_fields=["metric"],
            report_persisted=False,
            no_side_effects_status="passed",
            security_check_status="passed",
        ),
    )

    assert passed.passed
    assert passed.clarification_missing_fields_correct
    assert passed.no_side_effects
    assert not wrong_slot.passed
    assert "clarification_missing_fields_correct" in wrong_slot.violations


def test_required_recommendation_action_must_be_persisted() -> None:
    case = _case(expected_recommendation_actions=["下钻核验清单"])

    missing = evaluate_case(case, _observation())
    present = evaluate_case(
        case,
        _observation(
            actual_recommendation_actions=["根据已确认指标建立下钻核验清单。"]
        ),
    )

    assert not missing.passed
    assert "required_recommendation_actions_present" in missing.violations
    assert present.passed


def test_empty_chunk_allowlist_denies_returned_chunk() -> None:
    result = evaluate_case(
        _case(allowed_chunk_ids=[]),
        _observation(
            returned_chunk_ids=[101],
        ),
    )

    assert not result.citation_scope_correct
    assert "citation_scope_correct" in result.violations


def test_unspecified_chunk_allowlist_uses_frozen_document_scope() -> None:
    result = evaluate_case(
        _case(allowed_chunk_ids=None),
        _observation(returned_chunk_ids=[991]),
    )

    assert result.passed
    assert result.citation_scope_correct


def test_unknown_security_check_cannot_pass_the_hard_gate() -> None:
    _, metrics = evaluate_run(
        [_case()],
        [_observation(security_check_status="unknown", security_incidents=[])],
    )

    assert not metrics.hard_gate_passed
    assert metrics.hard_gate_status == "unknown"
    assert metrics.success_count == 0
    assert metrics.fail_count == 0
    assert metrics.unknown_count == 1
    assert metrics.applicable_count == 1


def test_unknown_citation_validation_is_not_a_failure_or_a_success() -> None:
    result = evaluate_case(_case(), _observation(citation_validation_status="unknown"))

    assert not result.passed
    assert result.hard_gate_status == "unknown"
    assert "citation_scope_correct" in result.unknown_checks
    assert "citation_scope_correct" not in result.violations


def test_unknown_numeric_validation_is_not_a_failure_or_a_success() -> None:
    result = evaluate_case(_case(), _observation(numeric_check_status="unknown"))

    assert not result.passed
    assert result.hard_gate_status == "unknown"
    assert "numeric_consistent" in result.unknown_checks
    assert "numeric_consistent" not in result.violations


def test_data_only_case_excludes_citation_gate_with_a_recorded_reason() -> None:
    result = evaluate_case(
        _case(
            expected_route="data_only",
            document_scope=[],
            allowed_chunk_ids=[],
            inapplicable_hard_gates={
                "citation_scope_correct": "data_only route does not consume documents"
            },
        ),
        _observation(
            actual_route="data_only",
            returned_chunk_ids=[],
            returned_document_paths=[],
            citation_validation_status="unknown",
        ),
    )

    assert result.passed
    assert result.inapplicable_checks == {
        "citation_scope_correct": "data_only route does not consume documents"
    }


def test_inapplicable_gate_requires_an_allowed_name_and_reason() -> None:
    try:
        evaluate_case(
            _case(inapplicable_hard_gates={"security_gate_passed": "not needed"}),
            _observation(),
        )
    except ValueError as error:
        assert "cannot be marked inapplicable" in str(error)
    else:
        raise AssertionError("security gate must remain applicable")


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


def test_run_reports_unknown_cost_without_a_false_settled_total() -> None:
    _, metrics = evaluate_run(
        [_case(), _case(case_id="second")],
        [
            _observation(cost="0.030000", cost_status="passed"),
            _observation(case_id="second", cost=None, cost_status="unknown"),
        ],
    )

    assert metrics.settled_cost is None
    assert metrics.cost_status == "unknown"


def test_sales_decline_fixture_is_versioned_and_has_isolated_heldout_cases() -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "sales_decline_v1.json"
    )
    fixture = EvaluationFixture.model_validate(
        json.loads(fixture_path.read_text(encoding="utf-8"))
    )
    assert len([case for case in fixture.cases if case.split == "development"]) == 5
    assert len([case for case in fixture.cases if case.split == "heldout"]) == 1


def test_business_gold_fixture_has_frozen_23_development_and_7_heldout_coverage() -> (
    None
):
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "business_gold_v1.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )

    assert fixture.dataset_version == "business-gold-v1"
    assert len(fixture.cases) == 30
    assert len({case.case_id for case in fixture.cases}) == 30
    assert len([case for case in fixture.cases if case.split == "development"]) == 23
    assert len([case for case in fixture.cases if case.split == "heldout"]) == 7
    assert all(case.coverage_tags for case in fixture.cases)
    assert Counter(case.coverage_tags[0] for case in fixture.cases) == {
        "planner": 4,
        "data_sql": 5,
        "knowledge_rag": 5,
        "reviewer_publish": 4,
        "security_scope": 4,
        "insufficient_refusal": 3,
        "collaboration": 5,
    }
    assert Counter(
        case.coverage_tags[0] for case in fixture.cases if case.split == "heldout"
    ) == {
        "planner": 1,
        "data_sql": 1,
        "knowledge_rag": 1,
        "reviewer_publish": 1,
        "security_scope": 1,
        "insufficient_refusal": 1,
        "collaboration": 1,
    }


def test_business_gold_fixture_matches_the_frozen_candidate_snapshot() -> None:
    fixture_path = (
        Path(__file__).parents[2] / "fixtures" / "evaluation" / "business_gold_v1.json"
    )

    assert hashlib.sha256(fixture_path.read_bytes()).hexdigest() == (
        "a110e7c31239d7883df42608bc829ea6248902d852c544cb4ebe0bda0048cc72"
    )


def test_knowledge_development_v1_1_explicitly_excludes_only_sql_gates() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_knowledge_development_v1_1.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )

    assert fixture.dataset_version == "business-knowledge-development-v1.1"
    assert len(fixture.cases) == 4
    assert all(case.split == "development" for case in fixture.cases)
    assert all(case.expected_route == "knowledge_only" for case in fixture.cases)
    assert all(
        set(case.inapplicable_hard_gates)
        == {"sql_result_equivalent", "numeric_consistent"}
        for case in fixture.cases
    )


def test_knowledge_development_v1_2_uses_document_term_contracts() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_knowledge_development_v1_2.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )

    assert fixture.dataset_version == "business-knowledge-development-v1.2"
    assert len(fixture.cases) == 4
    assert all(case.split == "development" for case in fixture.cases)
    assert all(case.expected_route == "knowledge_only" for case in fixture.cases)
    assert all(case.expected_document_claim_terms for case in fixture.cases)
    assert all(case.expected_document_limitation_terms for case in fixture.cases)
    assert all(not case.expected_supported_claims for case in fixture.cases)
    assert all(not case.expected_limitations for case in fixture.cases)


def test_knowledge_development_v1_3_scopes_limitations_to_the_question() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_knowledge_development_v1_3.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    cases = {case.case_id: case for case in fixture.cases}

    assert fixture.dataset_version == "business-knowledge-development-v1.3"
    assert all(case.split == "development" for case in cases.values())
    assert all(
        set(case.inapplicable_hard_gates)
        == {
            "entity_scope_correct",
            "sql_result_equivalent",
            "numeric_consistent",
        }
        for case in cases.values()
    )
    assert cases["knowledge-east-contract-evidence"].expected_outcome == "completed"
    assert [
        requirement.model_dump()
        for requirement in cases[
            "knowledge-east-contract-evidence"
        ].expected_document_claim_terms
    ] == [{"all_of": ["CUST-0001", "合同", "到期", "暂停采购"]}]
    assert not cases[
        "knowledge-east-contract-evidence"
    ].expected_document_limitation_terms
    assert cases["knowledge-quality-batch-evidence"].expected_outcome == "completed"
    assert not cases[
        "knowledge-quality-batch-evidence"
    ].expected_document_limitation_terms
    assert cases["knowledge-margin-two-factors"].expected_outcome == "completed"
    assert [
        requirement.model_dump()
        for requirement in cases[
            "knowledge-margin-two-factors"
        ].expected_document_qualification_terms
    ] == [{"all_of": ["不能", "只归因"]}]
    assert cases["knowledge-receivable-risk-boundary"].expected_outcome == "completed"
    assert not cases[
        "knowledge-receivable-risk-boundary"
    ].expected_document_limitation_terms


def test_knowledge_development_v1_4_uses_the_margin_source_qualification() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_knowledge_development_v1_4.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )
    cases = {case.case_id: case for case in fixture.cases}

    assert fixture.dataset_version == "business-knowledge-development-v1.4"
    assert [
        requirement.model_dump()
        for requirement in cases[
            "knowledge-margin-two-factors"
        ].expected_document_qualification_terms
    ] == [{"all_of": ["不支持", "只归因"]}]


def test_knowledge_development_v1_5_is_a_distinct_prefixed_development_case() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_knowledge_development_v1_5.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )

    assert fixture.dataset_version == "business-knowledge-development-v1.5"
    assert [case.case_id for case in fixture.cases] == [
        "knowledge-quality-batch-prefixed-evidence"
    ]
    assert all(case.split == "development" for case in fixture.cases)
    assert all(case.expected_route == "knowledge_only" for case in fixture.cases)


def test_knowledge_development_v1_6_is_an_empty_scope_insufficient_evidence_case() -> (
    None
):
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_knowledge_development_v1_6.json"
    )
    fixture = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    )

    assert fixture.dataset_version == "business-knowledge-development-v1.6"
    assert [case.case_id for case in fixture.cases] == [
        "knowledge-empty-supplier-certification-evidence"
    ]
    case = fixture.cases[0]
    assert case.split == "development"
    assert case.document_scope == []
    assert case.expected_route == "knowledge_only"
    assert case.expected_outcome == "insufficient_evidence"


def test_hybrid_insufficient_v2_has_an_executable_no_matching_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_hybrid_insufficient_development_v2.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_entities=["某新产品"],
            actual_period="2024-03",
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="insufficient_evidence",
            actual_limitations=["缺少能够支持原因判断的文档证据。"],
        ),
    )

    assert result.passed


def test_hybrid_insufficient_v8_has_an_executable_comparison_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_hybrid_insufficient_development_v8.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route="hybrid",
            actual_entities=["SKU-UNKNOWN-2024"],
            actual_period="2024-03 compared_to 2024-02",
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="insufficient_evidence",
            actual_limitations=["缺少能够支持原因判断的文档证据。"],
            model_calls=6,
            tokens=12000,
        ),
    )

    assert result.passed


def test_data_no_match_v3_has_an_executable_terminal_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_no_match_development_v3.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route="data_only",
            actual_entities=["不存在的测试区域"],
            actual_period="2025-08",
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="insufficient_evidence",
            actual_limitations=["经营数据未返回可确认的数字或记录。"],
        ),
    )

    assert result.passed


def test_clarification_v4_has_an_executable_terminal_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_clarification_development_v4.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route=None,
            actual_outcome="needs_clarification",
            actual_clarification_missing_fields=["time_range"],
            report_persisted=False,
            no_side_effects_status="passed",
            security_check_status="passed",
        ),
    )

    assert result.passed


def test_data_no_match_v5_has_an_executable_terminal_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_no_match_development_v5.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route="data_only",
            actual_entities=["华东区"],
            actual_period="2020-01",
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="insufficient_evidence",
            actual_limitations=["经营数据未返回可确认的数字或记录。"],
        ),
    )

    assert result.passed


def test_data_no_match_v6_has_an_executable_terminal_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_no_match_development_v6.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route="data_only",
            actual_entities=["华东区"],
            actual_period="2020-02",
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="insufficient_evidence",
            actual_limitations=["经营数据未返回可确认的数字或记录。"],
        ),
    )

    assert result.passed


def test_data_no_match_v7_has_an_executable_terminal_contract() -> None:
    fixture_path = (
        Path(__file__).parents[2]
        / "fixtures"
        / "evaluation"
        / "business_data_no_match_development_v7.json"
    )
    case = EvaluationFixture.model_validate_json(
        fixture_path.read_text(encoding="utf-8")
    ).cases[0]

    result = evaluate_case(
        case,
        _observation(
            case_id=case.case_id,
            actual_route="data_only",
            actual_entities=["华东区"],
            actual_period="2020-03",
            actual_result_fingerprint=case.expected_result_fingerprint,
            actual_confirmed_facts=[],
            actual_supported_claims=[],
            returned_chunk_ids=[],
            returned_document_paths=[],
            actual_outcome="insufficient_evidence",
            actual_limitations=["经营数据未返回可确认的数字或记录。"],
            model_calls=4,
            tokens=6831,
            duration_ms=8081,
            cost="0.002541",
        ),
    )

    assert result.passed


def test_missing_persisted_entity_scope_is_unknown() -> None:
    result = evaluate_case(
        _case(),
        _observation(actual_entities=None),
    )

    assert not result.passed
    assert result.hard_gate_status == "unknown"
    assert "entity_scope_correct" in result.unknown_checks
    assert "entity_scope_correct" not in result.violations


def test_missing_actual_period() -> None:
    result = evaluate_case(
        _case(),
        _observation(actual_period=None),
    )

    assert not result.passed
    assert result.hard_gate_status == "unknown"
    assert "entity_scope_correct" in result.unknown_checks
    assert "entity_scope_correct" not in result.violations


def test_missing_actual_result_fingerprint() -> None:
    result = evaluate_case(
        _case(),
        _observation(actual_result_fingerprint=None),
    )

    assert not result.passed
    assert result.hard_gate_status == "unknown"
    assert "sql_result_equivalent" in result.unknown_checks
    assert "sql_result_equivalent" not in result.violations


def test_knowledge_only_case_can_explicitly_exclude_sql_gates() -> None:
    case = _case(
        expected_route="knowledge_only",
        inapplicable_hard_gates={
            "entity_scope_correct": "文档路线由冻结文档和引用范围证明授权。",
            "sql_result_equivalent": "知识库专用路线不执行 SQL。",
            "numeric_consistent": "知识库专用路线没有 SQL 数值输出。",
        },
    )

    result = evaluate_case(
        case,
        _observation(
            actual_route="knowledge_only",
            actual_result_fingerprint=None,
            numeric_check_status="unknown",
        ),
    )

    assert "sql_result_equivalent" not in result.unknown_checks
    assert "numeric_consistent" not in result.unknown_checks
    assert "entity_scope_correct" not in result.unknown_checks
    assert result.passed


def test_document_term_expectations_accept_wording_without_literal_sentence_match() -> (
    None
):
    case = _case(
        expected_route="knowledge_only",
        expected_supported_claims=[],
        expected_document_claim_terms=[{"all_of": ["合同", "到期", "暂停采购"]}],
        expected_outcome="partial",
        expected_limitations=[],
        expected_document_limitation_terms=[{"all_of": ["续约", "确认"]}],
        inapplicable_hard_gates={
            "sql_result_equivalent": "知识库专用路线不执行 SQL。",
            "numeric_consistent": "知识库专用路线没有 SQL 数值输出。",
        },
    )

    result = evaluate_case(
        case,
        _observation(
            actual_route="knowledge_only",
            actual_result_fingerprint=None,
            actual_supported_claims=["资料说明合同已到期，客户暂停采购。"],
            actual_outcome="partial",
            actual_limitations=["续约结果仍需人工确认。"],
            numeric_check_status="unknown",
        ),
    )

    assert result.passed


def test_document_term_expectations_reject_a_missing_required_term() -> None:
    case = _case(
        expected_route="knowledge_only",
        expected_supported_claims=[],
        expected_document_claim_terms=[{"all_of": ["合同", "到期", "暂停采购"]}],
        expected_limitations=[],
        inapplicable_hard_gates={
            "sql_result_equivalent": "知识库专用路线不执行 SQL。",
            "numeric_consistent": "知识库专用路线没有 SQL 数值输出。",
        },
    )

    result = evaluate_case(
        case,
        _observation(
            actual_route="knowledge_only",
            actual_result_fingerprint=None,
            actual_supported_claims=["资料说明合同已到期。"],
            numeric_check_status="unknown",
        ),
    )

    assert result.required_claims_supported is False
    assert "required_claims_supported" in result.violations


def test_document_term_expectations_allow_a_controlled_action_object_modifier() -> None:
    case = _case(
        expected_route="knowledge_only",
        expected_supported_claims=[],
        expected_document_claim_terms=[
            {"all_of": ["CUST-0001", "合同", "到期", "暂停采购"]}
        ],
        expected_limitations=[],
        inapplicable_hard_gates={
            "sql_result_equivalent": "知识库专用路线不执行 SQL。",
            "numeric_consistent": "知识库专用路线没有 SQL 数值输出。",
        },
    )

    result = evaluate_case(
        case,
        _observation(
            actual_route="knowledge_only",
            actual_result_fingerprint=None,
            actual_supported_claims=[
                "CUST-0001合同到期，CRM记录客户暂停常规采购、等待重新谈判。"
            ],
            numeric_check_status="unknown",
        ),
    )

    assert result.required_claims_supported is True


def test_document_term_expectations_reject_an_unapproved_action_object_modifier() -> (
    None
):
    case = _case(
        expected_route="knowledge_only",
        expected_supported_claims=[],
        expected_document_claim_terms=[{"all_of": ["暂停采购"]}],
        expected_limitations=[],
        inapplicable_hard_gates={
            "sql_result_equivalent": "知识库专用路线不执行 SQL。",
            "numeric_consistent": "知识库专用路线没有 SQL 数值输出。",
        },
    )

    result = evaluate_case(
        case,
        _observation(
            actual_route="knowledge_only",
            actual_result_fingerprint=None,
            actual_supported_claims=["资料显示客户暂停非采购业务。"],
            numeric_check_status="unknown",
        ),
    )

    assert result.required_claims_supported is False


def test_document_term_expectations_reject_a_negated_literal() -> None:
    case = _case(
        expected_route="knowledge_only",
        expected_supported_claims=[],
        expected_document_claim_terms=[{"all_of": ["暂停采购"]}],
        expected_limitations=[],
        inapplicable_hard_gates={
            "sql_result_equivalent": "知识库专用路线不执行 SQL。",
            "numeric_consistent": "知识库专用路线没有 SQL 数值输出。",
        },
    )

    result = evaluate_case(
        case,
        _observation(
            actual_route="knowledge_only",
            actual_result_fingerprint=None,
            actual_supported_claims=["CRM记录客户没有暂停采购。"],
            numeric_check_status="unknown",
        ),
    )

    assert result.required_claims_supported is False


def test_document_qualification_terms_are_independent_of_partial_limitations() -> None:
    case = _case(
        expected_route="knowledge_only",
        expected_supported_claims=[],
        expected_document_claim_terms=[{"all_of": ["采购", "成本"]}],
        expected_document_qualification_terms=[{"all_of": ["不能", "只归因"]}],
        expected_outcome="completed",
        expected_limitations=[],
        inapplicable_hard_gates={
            "entity_scope_correct": "文档路线由冻结文档和引用范围证明授权。",
            "sql_result_equivalent": "知识库专用路线不执行 SQL。",
            "numeric_consistent": "知识库专用路线没有 SQL 数值输出。",
        },
    )
    result = evaluate_case(
        case,
        _observation(
            actual_route="knowledge_only",
            actual_entities=None,
            actual_period=None,
            actual_result_fingerprint=None,
            actual_supported_claims=["采购成本上升是候选因素。"],
            actual_document_qualifications=["文档不能支持只归因于其中任一因素。"],
            actual_outcome="completed",
            actual_limitations=[],
            numeric_check_status="unknown",
        ),
    )

    assert result.passed
    assert result.document_qualifications_supported is True
    assert result.limitations_correct is True


@pytest.mark.parametrize("gate", ["sql_result_equivalent", "entity_scope_correct"])
def test_data_case_cannot_mark_route_specific_gates_inapplicable(gate: str) -> None:
    with pytest.raises(ValueError, match="knowledge_only"):
        _case(inapplicable_hard_gates={gate: "不应绕过数据路线。"})


def test_missing_returned_document_paths() -> None:
    result = evaluate_case(
        _case(),
        _observation(returned_document_paths=None),
    )
    assert not result.passed
    assert result.hard_gate_status == "unknown"
    assert "citation_scope_correct" in result.unknown_checks
    assert "citation_scope_correct" not in result.violations


def test_out_of_scope_document_path_fails_hard_gate() -> None:
    result = evaluate_case(
        _case(),
        _observation(returned_document_paths=["events/other-company-private.md"]),
    )

    assert not result.passed
    assert result.hard_gate_status == "failed"
    assert "citation_scope_correct" in result.violations
    assert "citation_scope_correct" not in result.unknown_checks
