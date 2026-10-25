"""Versioned, deterministic contracts for business-analysis evaluation."""

import re
from datetime import datetime
from typing import Any, Literal

from app.modules.analysis.data.query_contract import ClarificationSlot
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Outcome = Literal[
    "completed",
    "partial",
    "failed",
    "cancelled",
    "insufficient_evidence",
    "needs_clarification",
]
Split = Literal["development", "heldout"]
CheckStatus = Literal["passed", "failed", "unknown"]
ExecutionFenceState = Literal[
    "cancelled_without_result", "replacement_result_preserved"
]
EvaluationKind = Literal[
    "analysis",
    "security_rejection",
    "runtime_tool_rejection",
    "sql_validation_rejection",
    "sql_timeout",
    "sql_result_limit",
    "duplicate_delivery",
    "execution_fence",
    "clarification",
]
ObservationSource = Literal[
    "persisted_task",
    "request_rejection",
    "runtime_tool_rejection",
    "sql_validation_rejection",
    "sql_timeout",
    "sql_result_limit",
    "duplicate_delivery",
    "execution_fence",
    "simulated",
]


class RequiredTerms(BaseModel):
    """A deterministic, wording-tolerant expectation for one reported item."""

    model_config = ConfigDict(extra="forbid")

    all_of: list[str] = Field(min_length=1)

    @field_validator("all_of")
    @classmethod
    def terms_are_nonempty_and_distinct(cls, value: list[str]) -> list[str]:
        normalized = [term.strip() for term in value]
        if any(not term for term in normalized):
            raise ValueError("required terms cannot be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("required terms cannot repeat")
        return normalized


class EvaluationCase(BaseModel):
    """One immutable business outcome contract; no answer key is sent to the Agent."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    complexity: Literal["simple", "medium", "complex"]
    split: Split
    evaluation_kind: EvaluationKind = "analysis"
    # A frozen Gold set records why each case exists, so quality improvements
    # cannot silently erase a safety, recovery, or collaboration scenario.
    coverage_tags: list[str] = Field(default_factory=list)
    question: str = Field(min_length=1)
    company_scope: str = Field(min_length=1)
    document_scope: list[str] = Field(default_factory=list)
    # Clarification and refusal are valid terminal decisions before a business
    # route exists, so Gold must be able to assert an intentional null route.
    expected_route: Literal["data_only", "knowledge_only", "hybrid"] | None
    expected_entities: list[str] = Field(min_length=1)
    expected_period: str = Field(min_length=1)
    expected_clarification_missing_fields: list[ClarificationSlot] = Field(
        default_factory=list, max_length=3
    )
    expected_query_requirements: list[str] = Field(min_length=1)
    expected_result_fingerprint: dict[str, Any] = Field(min_length=1)
    expected_semantic_result_fingerprint: dict[str, str] | None = None
    expected_confirmed_facts: list[str] = Field(default_factory=list)
    expected_supported_claims: list[str] = Field(default_factory=list)
    # Frozen-document fixtures use terms rather than one brittle generated
    # sentence. Citation scope remains an independent hard gate.
    expected_document_claim_terms: list[RequiredTerms] = Field(default_factory=list)
    expected_document_qualification_terms: list[RequiredTerms] = Field(
        default_factory=list
    )
    # These are operator-facing next actions, not unverified causal claims.
    expected_recommendation_actions: list[str] = Field(default_factory=list)
    # ``None`` means this frozen case uses document-path scope because runtime
    # chunk IDs are tenant-local.  An explicit empty list remains a denial.
    allowed_chunk_ids: list[int] | None = None
    inapplicable_hard_gates: dict[str, str] = Field(default_factory=dict)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_outcome: Outcome
    expected_limitations: list[str] = Field(default_factory=list)
    expected_document_limitation_terms: list[RequiredTerms] = Field(
        default_factory=list
    )
    expected_tool_denial_codes: list[str] = Field(default_factory=list)
    expected_sql_validation_codes: list[str] = Field(default_factory=list)
    expected_sql_timeout_codes: list[str] = Field(default_factory=list)
    expected_sql_result_max_rows: int | None = Field(default=None, ge=1)
    expected_duplicate_delivery_codes: list[str] = Field(default_factory=list)
    expected_execution_fence_codes: list[str] = Field(default_factory=list)
    expected_execution_fence_state: ExecutionFenceState | None = None
    max_model_calls: int = Field(ge=0)
    max_tokens: int = Field(ge=0)

    @field_validator("expected_semantic_result_fingerprint")
    @classmethod
    def semantic_result_fingerprint_is_sha256(
        cls, value: dict[str, str] | None
    ) -> dict[str, str] | None:
        if value is None:
            return None
        if (
            value.get("algorithm") != "sha256"
            or re.fullmatch(r"[0-9a-f]{64}", value.get("value", "")) is None
            or set(value) != {"algorithm", "value"}
        ):
            raise ValueError("semantic result fingerprint must be a SHA-256 value")
        return value

    @model_validator(mode="after")
    def validates_route_specific_inapplicable_gates(self) -> "EvaluationCase":
        if self.evaluation_kind == "clarification":
            if self.expected_outcome != "needs_clarification":
                raise ValueError("clarification cases must expect needs_clarification")
            if self.expected_route is not None:
                raise ValueError("clarification cases must have a null route")
            if not self.expected_clarification_missing_fields:
                raise ValueError(
                    "clarification cases require expected clarification fields"
                )
            if self.document_scope:
                raise ValueError("clarification cases must not freeze documents")
        elif self.evaluation_kind == "runtime_tool_rejection":
            if self.expected_outcome != "failed":
                raise ValueError("runtime tool rejection cases must expect failed")
            if self.expected_route is not None:
                raise ValueError("runtime tool rejection cases must have a null route")
            if not self.expected_tool_denial_codes:
                raise ValueError(
                    "runtime tool rejection cases require expected tool denial codes"
                )
            if self.max_model_calls != 0 or self.max_tokens != 0:
                raise ValueError(
                    "runtime tool rejection cases must have a zero model budget"
                )
        elif self.evaluation_kind == "sql_validation_rejection":
            if self.expected_outcome != "failed":
                raise ValueError("sql validation rejection cases must expect failed")
            if self.expected_route is not None:
                raise ValueError(
                    "sql validation rejection cases must have a null route"
                )
            if not self.expected_sql_validation_codes:
                raise ValueError(
                    "sql validation rejection cases require expected validation codes"
                )
            if self.max_model_calls != 0 or self.max_tokens != 0:
                raise ValueError(
                    "sql validation rejection cases must have a zero model budget"
                )
        elif self.evaluation_kind == "sql_timeout":
            if self.expected_outcome != "failed":
                raise ValueError("sql timeout cases must expect failed")
            if self.expected_route is not None:
                raise ValueError("sql timeout cases must have a null route")
            if not self.expected_sql_timeout_codes:
                raise ValueError("sql timeout cases require expected timeout codes")
            if self.max_model_calls != 0 or self.max_tokens != 0:
                raise ValueError("sql timeout cases must have a zero model budget")
        elif self.evaluation_kind == "sql_result_limit":
            if self.expected_outcome != "completed":
                raise ValueError("sql result limit cases must expect completed")
            if self.expected_route is not None:
                raise ValueError("sql result limit cases must have a null route")
            if self.expected_sql_result_max_rows is None:
                raise ValueError("sql result limit cases require a maximum row count")
            if self.max_model_calls != 0 or self.max_tokens != 0:
                raise ValueError("sql result limit cases must have a zero model budget")
        elif self.evaluation_kind == "duplicate_delivery":
            if self.expected_outcome != "completed":
                raise ValueError("duplicate delivery cases must expect completed")
            if self.expected_route is not None:
                raise ValueError("duplicate delivery cases must have a null route")
            if not self.expected_duplicate_delivery_codes:
                raise ValueError(
                    "duplicate delivery cases require expected rejection codes"
                )
            if self.max_model_calls != 0 or self.max_tokens != 0:
                raise ValueError(
                    "duplicate delivery cases must have a zero model budget"
                )
        elif self.evaluation_kind == "execution_fence":
            if self.expected_outcome not in {"cancelled", "completed"}:
                raise ValueError(
                    "execution fence cases must expect cancelled or completed"
                )
            if self.expected_route is not None:
                raise ValueError("execution fence cases must have a null route")
            if not self.expected_execution_fence_codes:
                raise ValueError(
                    "execution fence cases require expected rejection codes"
                )
            if self.expected_execution_fence_state is None:
                raise ValueError("execution fence cases require an expected state")
            if (
                self.expected_execution_fence_state == "cancelled_without_result"
                and self.expected_outcome != "cancelled"
            ):
                raise ValueError("cancelled fence state must expect cancelled")
            if (
                self.expected_execution_fence_state == "replacement_result_preserved"
                and self.expected_outcome != "completed"
            ):
                raise ValueError("replacement fence state must expect completed")
            if self.max_model_calls != 0 or self.max_tokens != 0:
                raise ValueError("execution fence cases must have a zero model budget")
        elif self.expected_clarification_missing_fields:
            raise ValueError("only clarification cases may expect clarification fields")
        if (
            self.evaluation_kind != "runtime_tool_rejection"
            and self.expected_tool_denial_codes
        ):
            raise ValueError(
                "only runtime tool rejection cases may expect tool denial codes"
            )
        if (
            self.evaluation_kind != "sql_validation_rejection"
            and self.expected_sql_validation_codes
        ):
            raise ValueError(
                "only sql validation rejection cases may expect validation codes"
            )
        if self.evaluation_kind != "sql_timeout" and self.expected_sql_timeout_codes:
            raise ValueError("only sql timeout cases may expect timeout codes")
        if (
            self.evaluation_kind != "duplicate_delivery"
            and self.expected_duplicate_delivery_codes
        ):
            raise ValueError("only duplicate delivery cases may expect rejection codes")
        if (
            self.evaluation_kind != "sql_result_limit"
            and self.expected_sql_result_max_rows is not None
        ):
            raise ValueError(
                "only sql result limit cases may expect a maximum row count"
            )
        if self.evaluation_kind != "execution_fence" and (
            self.expected_execution_fence_codes
            or self.expected_execution_fence_state is not None
        ):
            raise ValueError("only execution fence cases may expect rejection codes")
        sql_gates = {"sql_result_equivalent", "numeric_consistent"}
        requested = set(self.inapplicable_hard_gates)
        unknown = requested - {
            "citation_scope_correct",
            "entity_scope_correct",
            *sql_gates,
        }
        if unknown:
            raise ValueError(
                f"hard gates cannot be marked inapplicable: {sorted(unknown)}"
            )
        if requested & sql_gates and self.expected_route != "knowledge_only":
            raise ValueError(
                "SQL gates may be inapplicable only for knowledge_only cases"
            )
        if (
            "entity_scope_correct" in requested
            and self.expected_route != "knowledge_only"
        ):
            raise ValueError(
                "entity scope may be inapplicable only for knowledge_only cases"
            )
        document_terms = (
            self.expected_document_claim_terms
            or self.expected_document_qualification_terms
            or self.expected_document_limitation_terms
        )
        if document_terms and self.expected_route not in {"knowledge_only", "hybrid"}:
            raise ValueError(
                "document term expectations require a knowledge_only or hybrid route"
            )
        empty_scope_refusal = (
            self.expected_route == "knowledge_only"
            and self.expected_outcome == "insufficient_evidence"
            and self.expected_document_limitation_terms
            and not self.expected_document_claim_terms
            and not self.expected_document_qualification_terms
        )
        if document_terms and not self.document_scope and not empty_scope_refusal:
            raise ValueError(
                "document term expectations require a frozen document scope"
            )
        if document_terms and (
            self.expected_supported_claims or self.expected_limitations
        ):
            raise ValueError(
                "document term expectations must not be combined with literal expectations"
            )
        return self


class EvaluationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    dataset_version: str = Field(min_length=1)
    cases: list[EvaluationCase] = Field(min_length=1)


class EvaluationObservation(BaseModel):
    """Normalized result facts with an explicit real or simulated source."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    source: ObservationSource = "persisted_task"
    actual_route: str | None = None
    # Privacy-safe control-flow diagnostics retained after disposable-task cleanup.
    actual_plan_intent_kind: str | None = None
    knowledge_result_status: str | None = None
    knowledge_evidence_count: int | None = Field(default=None, ge=0)
    semantic_review_verdict: str | None = None
    reviewer_citation_chunk_count: int | None = Field(default=None, ge=0)
    actual_entities: list[str] | None = None
    actual_period: str | None = None
    actual_clarification_missing_fields: list[ClarificationSlot] | None = None
    actual_data_status: str | None = None
    actual_data_error_code: str | None = None
    actual_result_fingerprint: dict[str, Any] | None = None
    actual_semantic_result_fingerprint: dict[str, str] | None = None
    actual_confirmed_facts: list[str] = Field(default_factory=list)
    actual_supported_claims: list[str] = Field(default_factory=list)
    actual_document_qualifications: list[str] = Field(default_factory=list)
    actual_recommendation_actions: list[str] = Field(default_factory=list)
    returned_chunk_ids: list[int] = Field(default_factory=list)
    returned_document_paths: list[str] | None = None
    actual_outcome: Outcome
    actual_limitations: list[str] = Field(default_factory=list)
    # Provider-model calls and local embedding/rerank resources have different
    # budgets and cost semantics; neither may be silently folded into the other.
    model_calls: int = Field(ge=0)
    provider_model_calls_by_node: dict[str, int] = Field(default_factory=dict)
    local_resource_calls: int = Field(default=0, ge=0)
    tokens: int = Field(ge=0)
    report_persisted: bool
    numeric_checks_passed: bool
    numeric_check_status: CheckStatus = "unknown"
    deterministic_validation_passed: bool
    deterministic_validation_status: CheckStatus = "unknown"
    citation_validation_status: CheckStatus = "unknown"
    security_incidents: list[str] = Field(default_factory=list)
    # Older or incomplete telemetry must remain visible as unknown instead of
    # being silently treated as a clean security result.
    security_check_status: CheckStatus = "unknown"
    # A rejection adapter must explicitly supply these facts; an ordinary
    # persisted task cannot be mistaken for evidence of a denied request.
    rejection_observed_status: CheckStatus = "unknown"
    no_side_effects_status: CheckStatus = "unknown"
    runtime_tool_denial_status: CheckStatus = "unknown"
    tool_execution_prevented_status: CheckStatus = "unknown"
    actual_tool_denial_codes: list[str] = Field(default_factory=list)
    sql_validation_rejection_status: CheckStatus = "unknown"
    business_result_prevented_status: CheckStatus = "unknown"
    actual_sql_validation_codes: list[str] = Field(default_factory=list)
    sql_timeout_status: CheckStatus = "unknown"
    sql_timeout_result_prevented_status: CheckStatus = "unknown"
    actual_sql_timeout_codes: list[str] = Field(default_factory=list)
    sql_result_limit_status: CheckStatus = "unknown"
    actual_sql_result_row_count: int | None = Field(default=None, ge=0)
    duplicate_delivery_status: CheckStatus = "unknown"
    duplicate_execution_prevented_status: CheckStatus = "unknown"
    actual_duplicate_delivery_codes: list[str] = Field(default_factory=list)
    execution_fence_status: CheckStatus = "unknown"
    late_execution_write_prevented_status: CheckStatus = "unknown"
    actual_execution_fence_codes: list[str] = Field(default_factory=list)
    actual_execution_fence_state: ExecutionFenceState | None = None
    # End-to-end duration remains the user-visible lifecycle measurement. These
    # two fields make the human approval delay explicit instead of treating it
    # as Worker performance.
    duration_ms: int | None = Field(default=None, ge=0)
    machine_execution_duration_ms: int | None = Field(default=None, ge=0)
    human_review_wait_ms: int | None = Field(default=None, ge=0)
    # A numeric total is meaningful only when every related model ledger row
    # settled. Unknown reservations are intentionally not coerced to zero.
    cost: str | None = None
    cost_status: CheckStatus = "unknown"


class EvaluationCaseResult(BaseModel):
    case_id: str
    evaluation_kind: EvaluationKind
    passed: bool
    hard_gate_status: CheckStatus
    route_correct: bool | None
    clarification_missing_fields_correct: bool | None = None
    entity_scope_correct: bool | None
    sql_result_equivalent: bool | None
    numeric_consistent: bool | None
    citation_scope_correct: bool | None
    required_facts_confirmed: bool | None
    required_claims_supported: bool | None
    document_qualifications_supported: bool | None = None
    required_recommendation_actions_present: bool | None
    forbidden_claim_free: bool | None
    outcome_correct: bool
    limitations_correct: bool | None
    within_budget: bool
    report_persisted: bool | None
    deterministic_validation_passed: bool | None
    security_gate_passed: bool
    security_rejection_observed: bool | None = None
    no_side_effects: bool | None = None
    runtime_tool_denial_observed: bool | None = None
    tool_execution_prevented: bool | None = None
    sql_validation_rejection_observed: bool | None = None
    business_result_prevented: bool | None = None
    sql_timeout_observed: bool | None = None
    sql_timeout_result_prevented: bool | None = None
    sql_result_limit_observed: bool | None = None
    sql_result_row_count_within_limit: bool | None = None
    duplicate_delivery_observed: bool | None = None
    duplicate_execution_prevented: bool | None = None
    violations: list[str] = Field(default_factory=list)
    unknown_checks: list[str] = Field(default_factory=list)
    inapplicable_checks: dict[str, str] = Field(default_factory=dict)


class EvaluationMetrics(BaseModel):
    cases: int
    success_count: int
    applicable_count: int
    fail_count: int
    unknown_count: int
    partial_count: int
    trusted_business_analysis_success_rate: float | None
    route_accuracy: float | None
    sql_result_equivalence_rate: float | None
    numeric_consistency_rate: float | None
    citation_scope_correct_rate: float | None
    confirmed_fact_rate: float | None
    supported_claim_rate: float | None
    forbidden_claim_free_rate: float | None
    outcome_accuracy: float | None
    report_persisted_rate: float | None
    security_incident_count: int
    hard_gate_status: CheckStatus
    hard_gate_passed: bool
    duration_p95_ms: int | None
    machine_execution_duration_p95_ms: int | None = None
    human_review_wait_p95_ms: int | None = None
    model_calls: int
    tokens: int
    settled_cost: str | None
    cost_status: CheckStatus


class EvaluationRun(BaseModel):
    """Portable JSON artifact; filesystem persistence avoids an evaluation migration."""

    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    comparison_label: Literal["baseline", "candidate"]
    git_revision: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    environment: dict[str, str]
    parameters: dict[str, Any]
    # Keep normalized, privacy-safe diagnostics beside scores so a disposable
    # tenant can be cleaned without erasing the evidence needed to explain a
    # failed baseline.
    observations: list[EvaluationObservation] = Field(default_factory=list)
    results: list[EvaluationCaseResult]
    metrics: EvaluationMetrics
