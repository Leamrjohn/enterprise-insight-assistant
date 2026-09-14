"""Deterministic evaluator for persisted Worker observations, not an LLM judge."""

from math import ceil

from app.modules.evaluation.business_schemas import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationMetrics,
    EvaluationObservation,
)


def _contains_all(expected: list[str], actual: list[str]) -> bool:
    actual_text = "\n".join(actual)
    return all(value in actual_text for value in expected)


def evaluate_case(case: EvaluationCase, observation: EvaluationObservation) -> EvaluationCaseResult:
    if case.case_id != observation.case_id:
        raise ValueError("observation case_id must match evaluation case")
    route_correct = case.expected_route == observation.actual_route
    entity_scope_correct = (
        set(case.expected_entities).issubset(observation.actual_entities)
        and case.expected_period == observation.actual_period
    )
    sql_result_equivalent = case.expected_result_fingerprint == observation.actual_result_fingerprint
    numeric_consistent = observation.numeric_checks_passed
    citation_scope_correct = (
        (not case.allowed_chunk_ids or set(observation.returned_chunk_ids).issubset(case.allowed_chunk_ids))
        and set(observation.returned_document_paths).issubset(case.document_scope)
    )
    required_facts_confirmed = _contains_all(
        case.expected_confirmed_facts, observation.actual_confirmed_facts
    )
    required_claims_supported = _contains_all(
        case.expected_supported_claims, observation.actual_supported_claims
    )
    forbidden_claim_free = not any(
        claim in "\n".join(observation.actual_confirmed_facts + observation.actual_supported_claims)
        for claim in case.forbidden_claims
    )
    outcome_correct = case.expected_outcome == observation.actual_outcome
    limitations_correct = _contains_all(case.expected_limitations, observation.actual_limitations)
    within_budget = (
        observation.model_calls <= case.max_model_calls and observation.tokens <= case.max_tokens
    )
    security_gate_passed = not observation.security_incidents
    checks = {
        "route_correct": route_correct,
        "entity_scope_correct": entity_scope_correct,
        "sql_result_equivalent": sql_result_equivalent,
        "numeric_consistent": numeric_consistent,
        "citation_scope_correct": citation_scope_correct,
        "required_facts_confirmed": required_facts_confirmed,
        "required_claims_supported": required_claims_supported,
        "forbidden_claim_free": forbidden_claim_free,
        "outcome_correct": outcome_correct,
        "limitations_correct": limitations_correct,
        "within_budget": within_budget,
        "report_persisted": observation.report_persisted,
        "deterministic_validation_passed": observation.deterministic_validation_passed,
        "security_gate_passed": security_gate_passed,
    }
    violations = [name for name, passed in checks.items() if not passed]
    return EvaluationCaseResult(case_id=case.case_id, passed=not violations, violations=violations, **checks)


def _rate(results: list[EvaluationCaseResult], field: str) -> float:
    return sum(getattr(result, field) for result in results) / len(results)


def evaluate_run(
    cases: list[EvaluationCase], observations: list[EvaluationObservation]
) -> tuple[list[EvaluationCaseResult], EvaluationMetrics]:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    observations_by_case = {observation.case_id: observation for observation in observations}
    if len(observations_by_case) != len(observations):
        raise ValueError("duplicate evaluation observations are not allowed")
    missing = [case.case_id for case in cases if case.case_id not in observations_by_case]
    unexpected = set(observations_by_case) - {case.case_id for case in cases}
    if missing or unexpected:
        raise ValueError(f"observations must match cases exactly: missing={missing}, unexpected={sorted(unexpected)}")
    results = [evaluate_case(case, observations_by_case[case.case_id]) for case in cases]
    durations = sorted(observation.duration_ms for observation in observations if observation.duration_ms is not None)
    p95 = durations[max(0, ceil(len(durations) * 0.95) - 1)] if durations else None
    incidents = sum(len(observation.security_incidents) for observation in observations)
    metrics = EvaluationMetrics(
        cases=len(results),
        trusted_business_analysis_success_rate=_rate(results, "passed"),
        route_accuracy=_rate(results, "route_correct"),
        sql_result_equivalence_rate=_rate(results, "sql_result_equivalent"),
        numeric_consistency_rate=_rate(results, "numeric_consistent"),
        citation_scope_correct_rate=_rate(results, "citation_scope_correct"),
        confirmed_fact_rate=_rate(results, "required_facts_confirmed"),
        supported_claim_rate=_rate(results, "required_claims_supported"),
        forbidden_claim_free_rate=_rate(results, "forbidden_claim_free"),
        outcome_accuracy=_rate(results, "outcome_correct"),
        report_persisted_rate=_rate(results, "report_persisted"),
        security_incident_count=incidents,
        hard_gate_passed=incidents == 0,
        duration_p95_ms=p95,
        model_calls=sum(observation.model_calls for observation in observations),
        tokens=sum(observation.tokens for observation in observations),
    )
    return results, metrics
