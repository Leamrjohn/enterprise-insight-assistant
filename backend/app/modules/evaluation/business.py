"""Deterministic evaluator for persisted Worker observations, not an LLM judge."""

from decimal import Decimal, InvalidOperation
from math import ceil

from app.modules.analysis.semantic_catalog import FILTER_VALUE_DEFINITIONS
from app.modules.evaluation.business_schemas import (
    CheckStatus,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationKind,
    EvaluationMetrics,
    EvaluationObservation,
)

_REGISTERED_REGION_NAMES = frozenset(
    FILTER_VALUE_DEFINITIONS["customers.region_code"].values()
)


def _canonical_entity_scope(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith("区") and normalized[:-1] in _REGISTERED_REGION_NAMES:
        return normalized[:-1]
    return normalized


def _contains_all(expected: list[str], actual: list[str]) -> bool:
    actual_text = "\n".join(actual)
    return all(value in actual_text for value in expected)


_DOCUMENT_TERM_VARIANTS: dict[str, tuple[str, ...]] = {
    # A paused ordinary procurement status entails the broader paused-procurement
    # claim, but the inverse is not assumed. Keep this vocabulary explicit so a
    # fixture cannot silently gain fuzzy semantic matching.
    "暂停采购": ("暂停常规采购", "暂停日常采购", "暂停例行采购"),
}
_NEGATION_MARKERS = ("没有", "并没有", "并未", "未", "不", "非")
_QUALIFIED_NEGATION_MARKERS = (
    "不能证明",
    "不能仅凭",
    "不足以证明",
    "不能断言",
    "不支持",
    "无法证明",
    "无法断言",
    "未能证明",
)
_QUESTION_NEGATION_SUFFIX_MARKERS = ("不足以判断", "无法给出结论")


def _term_is_negated(item: str, start: int) -> bool:
    """Reject a literal or approved variant when its preceding clause negates it."""
    context = item[max(0, start - 4) : start]
    if any(marker in context for marker in _NEGATION_MARKERS):
        return True
    sentence_start = max(item.rfind(marker, 0, start) for marker in "。！？!?；;")
    qualified_context = item[sentence_start + 1 : start]
    if any(marker in qualified_context for marker in _QUALIFIED_NEGATION_MARKERS):
        return True
    sentence_end = min(
        (index for marker in "。！？!?；;" if (index := item.find(marker, start)) >= 0),
        default=len(item),
    )
    return "能否证明" in qualified_context and any(
        marker in item[start:sentence_end]
        for marker in _QUESTION_NEGATION_SUFFIX_MARKERS
    )


def _contains_document_term(term: str, item: str) -> bool:
    candidates = (term, *_DOCUMENT_TERM_VARIANTS.get(term, ()))
    for candidate in candidates:
        start = item.find(candidate)
        while start >= 0:
            if not _term_is_negated(item, start):
                return True
            start = item.find(candidate, start + 1)
    return False


def _contains_required_terms(
    expected: object, actual: list[str], *, reject_negated_claims: bool = False
) -> bool:
    """Require every term group in one returned item without using an LLM judge."""
    return all(
        any(
            all(
                _contains_document_term(term, item)
                if reject_negated_claims
                else term in item
                for term in requirement.all_of
            )
            for item in actual
        )
        for requirement in expected
    )


def _p95_duration(observations: list[EvaluationObservation], attribute: str) -> int | None:
    durations = sorted(
        value
        for observation in observations
        if isinstance((value := getattr(observation, attribute)), int)
    )
    return durations[max(0, ceil(len(durations) * 0.95) - 1)] if durations else None


def _and_status(statuses: list[CheckStatus]) -> CheckStatus:
    if "failed" in statuses:
        return "failed"
    if "unknown" in statuses:
        return "unknown"
    return "passed"


_INAPPLICABLE_HARD_GATES = {
    "citation_scope_correct",
    "entity_scope_correct",
    "sql_result_equivalent",
    "numeric_consistent",
}


def _is_sha256_result_fingerprint(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("algorithm") == "sha256"
        and isinstance(value.get("value"), str)
        and len(value["value"]) == 64
    )


def _security_rejection_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate a denied operation without requiring a business report."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    checks: dict[str, bool | CheckStatus] = {
        "rejection_observed": observation.rejection_observed_status,
        "no_side_effects": observation.no_side_effects_status,
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=None,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        security_rejection_observed=observation.rejection_observed_status == "passed",
        no_side_effects=observation.no_side_effects_status == "passed",
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
    )


def _runtime_tool_rejection_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate a durable Runtime denial without treating it as an HTTP rejection."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    checks: dict[str, bool | CheckStatus] = {
        "runtime_tool_denial": observation.runtime_tool_denial_status,
        "tool_execution_prevented": observation.tool_execution_prevented_status,
        "denial_codes_match": set(case.expected_tool_denial_codes).issubset(
            observation.actual_tool_denial_codes
        ),
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=None,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        runtime_tool_denial_observed=(
            observation.runtime_tool_denial_status == "passed"
        ),
        tool_execution_prevented=(
            observation.tool_execution_prevented_status == "passed"
        ),
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
    )


def _sql_validation_rejection_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate a persisted SQL validation failure without calling it a denial."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    checks: dict[str, bool | CheckStatus] = {
        "sql_validation_rejection": observation.sql_validation_rejection_status,
        "business_result_prevented": observation.business_result_prevented_status,
        "sql_validation_codes_match": set(
            case.expected_sql_validation_codes
        ).issubset(observation.actual_sql_validation_codes),
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=None,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        sql_validation_rejection_observed=(
            observation.sql_validation_rejection_status == "passed"
        ),
        business_result_prevented=(
            observation.business_result_prevented_status == "passed"
        ),
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
    )


def _sql_result_limit_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate a persisted SQL call whose returned rows stay capped."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    row_count_within_limit = (
        observation.actual_sql_result_row_count is not None
        and observation.actual_sql_result_row_count <= case.expected_sql_result_max_rows
    )
    checks: dict[str, bool | CheckStatus] = {
        "sql_result_limit": observation.sql_result_limit_status,
        "row_count_within_limit": row_count_within_limit,
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=None,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        sql_result_limit_observed=observation.sql_result_limit_status == "passed",
        sql_result_row_count_within_limit=row_count_within_limit,
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
    )


def _sql_timeout_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate a persisted SQL timeout without calling it a validation denial."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    checks: dict[str, bool | CheckStatus] = {
        "sql_timeout": observation.sql_timeout_status,
        "sql_timeout_result_prevented": observation.sql_timeout_result_prevented_status,
        "sql_timeout_codes_match": set(case.expected_sql_timeout_codes).issubset(
            observation.actual_sql_timeout_codes
        ),
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=None,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        sql_timeout_observed=observation.sql_timeout_status == "passed",
        sql_timeout_result_prevented=(
            observation.sql_timeout_result_prevented_status == "passed"
        ),
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
    )


def _duplicate_delivery_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate one rejected duplicate claim and a preserved single execution."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    checks: dict[str, bool | CheckStatus] = {
        "duplicate_delivery": observation.duplicate_delivery_status,
        "duplicate_execution_prevented": (
            observation.duplicate_execution_prevented_status
        ),
        "duplicate_delivery_codes_match": set(
            case.expected_duplicate_delivery_codes
        ).issubset(observation.actual_duplicate_delivery_codes),
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=None,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        duplicate_delivery_observed=(
            observation.duplicate_delivery_status == "passed"
        ),
        duplicate_execution_prevented=(
            observation.duplicate_execution_prevented_status == "passed"
        ),
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
    )


def _execution_fence_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate a persisted stale-write fence without calling it a tool denial."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    checks: dict[str, bool | CheckStatus] = {
        "execution_fence": observation.execution_fence_status,
        "late_execution_write_prevented": (
            observation.late_execution_write_prevented_status
        ),
        "rejection_codes_match": set(case.expected_execution_fence_codes).issubset(
            observation.actual_execution_fence_codes
        ),
        "fence_state_matches": (
            case.expected_execution_fence_state
            == observation.actual_execution_fence_state
        ),
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=None,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
    )


def _clarification_result(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    """Evaluate a pre-analysis clarification without treating it as a report."""
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    clarification_fields_correct = (
        observation.actual_clarification_missing_fields
        == case.expected_clarification_missing_fields
    )
    checks: dict[str, bool | CheckStatus] = {
        "route_correct": observation.actual_route is None,
        "clarification_missing_fields_correct": clarification_fields_correct,
        "no_side_effects": observation.no_side_effects_status,
        "outcome_correct": case.expected_outcome == observation.actual_outcome,
        "within_budget": (
            observation.model_calls <= case.max_model_calls
            and observation.tokens <= case.max_tokens
        ),
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    hard_gate_status = _and_status(list(statuses.values()))
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        route_correct=checks["route_correct"],
        clarification_missing_fields_correct=clarification_fields_correct,
        entity_scope_correct=None,
        sql_result_equivalent=None,
        numeric_consistent=None,
        citation_scope_correct=None,
        required_facts_confirmed=None,
        required_claims_supported=None,
        required_recommendation_actions_present=None,
        forbidden_claim_free=None,
        outcome_correct=checks["outcome_correct"],
        limitations_correct=None,
        within_budget=checks["within_budget"],
        report_persisted=None,
        deterministic_validation_passed=None,
        security_gate_passed=security_gate_status == "passed",
        no_side_effects=observation.no_side_effects_status == "passed",
        violations=[name for name, status in statuses.items() if status == "failed"],
        unknown_checks=[
            name for name, status in statuses.items() if status == "unknown"
        ],
        inapplicable_checks={
            "entity_scope_correct": "clarification terminates before business scope is resolved",
            "sql_result_equivalent": "clarification must not execute SQL",
            "numeric_consistent": "clarification has no business numeric result",
            "citation_scope_correct": "clarification must not retrieve documents",
        },
    )


def evaluate_case(
    case: EvaluationCase, observation: EvaluationObservation
) -> EvaluationCaseResult:
    if case.case_id != observation.case_id:
        raise ValueError("observation case_id must match evaluation case")
    if case.evaluation_kind == "security_rejection":
        return _security_rejection_result(case, observation)
    if case.evaluation_kind == "runtime_tool_rejection":
        return _runtime_tool_rejection_result(case, observation)
    if case.evaluation_kind == "sql_validation_rejection":
        return _sql_validation_rejection_result(case, observation)
    if case.evaluation_kind == "sql_timeout":
        return _sql_timeout_result(case, observation)
    if case.evaluation_kind == "sql_result_limit":
        return _sql_result_limit_result(case, observation)
    if case.evaluation_kind == "duplicate_delivery":
        return _duplicate_delivery_result(case, observation)
    if case.evaluation_kind == "execution_fence":
        return _execution_fence_result(case, observation)
    if case.evaluation_kind == "clarification":
        return _clarification_result(case, observation)
    route_correct = case.expected_route == observation.actual_route
    entity_scope_status: CheckStatus
    if observation.actual_entities is None or observation.actual_period is None:
        entity_scope_status = "unknown"
    else:
        entity_scope_status = (
            "passed"
            if (
                {
                    _canonical_entity_scope(entity)
                    for entity in case.expected_entities
                }.issubset(
                    {
                        _canonical_entity_scope(entity)
                        for entity in observation.actual_entities
                    }
                )
                and case.expected_period == observation.actual_period
            )
            else "failed"
        )
    sql_result_equivalent: CheckStatus
    expected_fingerprint = (
        case.expected_semantic_result_fingerprint
        if case.expected_semantic_result_fingerprint is not None
        else case.expected_result_fingerprint
    )
    actual_fingerprint = (
        observation.actual_semantic_result_fingerprint
        if case.expected_semantic_result_fingerprint is not None
        else observation.actual_result_fingerprint
    )
    if actual_fingerprint is None or (
        _is_sha256_result_fingerprint(actual_fingerprint)
        != _is_sha256_result_fingerprint(expected_fingerprint)
    ):
        sql_result_equivalent = "unknown"
    else:
        sql_result_equivalent = (
            "passed"
            if expected_fingerprint == actual_fingerprint
            else "failed"
        )
    numeric_consistent = observation.numeric_check_status == "passed"

    citation_scope_status: CheckStatus
    if observation.citation_validation_status == "failed" or (
        case.allowed_chunk_ids is not None
        and not set(observation.returned_chunk_ids).issubset(case.allowed_chunk_ids)
    ):
        citation_scope_status = "failed"
    elif observation.returned_document_paths is None:
        citation_scope_status = "unknown"
    elif not set(observation.returned_document_paths).issubset(case.document_scope):
        citation_scope_status = "failed"
    else:
        citation_scope_status = observation.citation_validation_status

    required_facts_confirmed = _contains_all(
        case.expected_confirmed_facts, observation.actual_confirmed_facts
    )
    required_claims_supported = _contains_all(
        case.expected_supported_claims, observation.actual_supported_claims
    ) and _contains_required_terms(
        case.expected_document_claim_terms,
        observation.actual_supported_claims,
        reject_negated_claims=True,
    )
    document_qualifications_supported = _contains_required_terms(
        case.expected_document_qualification_terms,
        observation.actual_document_qualifications,
    )
    required_recommendation_actions_present = _contains_all(
        case.expected_recommendation_actions,
        observation.actual_recommendation_actions,
    )
    forbidden_claim_free = not any(
        _contains_document_term(claim, item)
        for claim in case.forbidden_claims
        for item in (
            observation.actual_confirmed_facts + observation.actual_supported_claims
        )
    )
    outcome_correct = case.expected_outcome == observation.actual_outcome
    limitations_correct = _contains_all(
        case.expected_limitations, observation.actual_limitations
    ) and _contains_required_terms(
        case.expected_document_limitation_terms, observation.actual_limitations
    )
    within_budget = (
        observation.model_calls <= case.max_model_calls
        and observation.tokens <= case.max_tokens
    )
    security_gate_status: CheckStatus = (
        "failed"
        if observation.security_incidents
        else observation.security_check_status
    )
    checks: dict[str, bool | CheckStatus] = {
        "route_correct": route_correct,
        "entity_scope_correct": entity_scope_status,
        "sql_result_equivalent": sql_result_equivalent,
        "numeric_consistent": observation.numeric_check_status,
        "citation_scope_correct": citation_scope_status,
        "required_facts_confirmed": required_facts_confirmed,
        "required_claims_supported": required_claims_supported,
        "document_qualifications_supported": document_qualifications_supported,
        "required_recommendation_actions_present": required_recommendation_actions_present,
        "forbidden_claim_free": forbidden_claim_free,
        "outcome_correct": outcome_correct,
        "limitations_correct": limitations_correct,
        "within_budget": within_budget,
        "report_persisted": observation.report_persisted,
        "deterministic_validation_passed": observation.deterministic_validation_status,
        "security_gate_passed": security_gate_status,
    }
    statuses = {
        name: value if isinstance(value, str) else ("passed" if value else "failed")
        for name, value in checks.items()
    }
    inapplicable_checks = case.inapplicable_hard_gates
    for name, reason in inapplicable_checks.items():
        if name not in _INAPPLICABLE_HARD_GATES:
            raise ValueError(f"hard gate cannot be marked inapplicable: {name}")
        if not reason.strip():
            raise ValueError(f"inapplicable hard gate requires a reason: {name}")
    applicable_statuses = {
        name: status
        for name, status in statuses.items()
        if name not in inapplicable_checks
    }
    hard_gate_status = _and_status(list(applicable_statuses.values()))
    violations = [
        name for name, status in applicable_statuses.items() if status == "failed"
    ]
    unknown_checks = [
        name for name, status in applicable_statuses.items() if status == "unknown"
    ]
    return EvaluationCaseResult(
        case_id=case.case_id,
        evaluation_kind=case.evaluation_kind,
        passed=hard_gate_status == "passed",
        hard_gate_status=hard_gate_status,
        citation_scope_correct=citation_scope_status == "passed",
        security_gate_passed=security_gate_status == "passed",
        entity_scope_correct=entity_scope_status == "passed",
        sql_result_equivalent=sql_result_equivalent == "passed",
        numeric_consistent=numeric_consistent,
        deterministic_validation_passed=observation.deterministic_validation_status
        == "passed",
        violations=violations,
        unknown_checks=unknown_checks,
        inapplicable_checks=inapplicable_checks,
        **{
            name: value
            for name, value in checks.items()
            if name
            not in {
                "numeric_consistent",
                "citation_scope_correct",
                "deterministic_validation_passed",
                "security_gate_passed",
                "entity_scope_correct",
                "sql_result_equivalent",
            }
        },
    )


def _rate(
    results: list[EvaluationCaseResult],
    field: str,
    *,
    kind: EvaluationKind = "analysis",
) -> float | None:
    applicable_results = [
        result
        for result in results
        if result.evaluation_kind == kind
        and field not in result.inapplicable_checks
        and getattr(result, field) is not None
    ]
    if not applicable_results:
        return None
    return sum(getattr(result, field) for result in applicable_results) / len(
        applicable_results
    )


def evaluate_run(
    cases: list[EvaluationCase], observations: list[EvaluationObservation]
) -> tuple[list[EvaluationCaseResult], EvaluationMetrics]:
    if not cases:
        raise ValueError("at least one evaluation case is required")
    observations_by_case = {
        observation.case_id: observation for observation in observations
    }
    if len(observations_by_case) != len(observations):
        raise ValueError("duplicate evaluation observations are not allowed")
    missing = [
        case.case_id for case in cases if case.case_id not in observations_by_case
    ]
    unexpected = set(observations_by_case) - {case.case_id for case in cases}
    if missing or unexpected:
        raise ValueError(
            f"observations must match cases exactly: missing={missing}, unexpected={sorted(unexpected)}"
        )
    results = [
        evaluate_case(case, observations_by_case[case.case_id]) for case in cases
    ]
    p95 = _p95_duration(observations, "duration_ms")
    machine_execution_p95 = _p95_duration(
        observations, "machine_execution_duration_ms"
    )
    human_review_wait_p95 = _p95_duration(observations, "human_review_wait_ms")
    incidents = sum(len(observation.security_incidents) for observation in observations)
    statuses = [result.hard_gate_status for result in results]
    hard_gate_status = _and_status(statuses)
    cost_status = _and_status([observation.cost_status for observation in observations])
    settled_cost: str | None = None
    if cost_status == "passed":
        try:
            settled_cost = format(
                sum(
                    (Decimal(observation.cost) for observation in observations),
                    Decimal(0),
                ).quantize(Decimal("0.000001")),
                "f",
            )
        except (InvalidOperation, TypeError):
            cost_status = "unknown"
    metrics = EvaluationMetrics(
        cases=len(results),
        success_count=statuses.count("passed"),
        applicable_count=len(results),
        fail_count=statuses.count("failed"),
        unknown_count=statuses.count("unknown"),
        partial_count=sum(
            observation.actual_outcome == "partial" for observation in observations
        ),
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
        hard_gate_status=hard_gate_status,
        hard_gate_passed=hard_gate_status == "passed",
        duration_p95_ms=p95,
        machine_execution_duration_p95_ms=machine_execution_p95,
        human_review_wait_p95_ms=human_review_wait_p95,
        model_calls=sum(observation.model_calls for observation in observations),
        tokens=sum(observation.tokens for observation in observations),
        settled_cost=settled_cost,
        cost_status=cost_status,
    )
    return results, metrics
