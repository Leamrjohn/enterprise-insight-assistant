"""Versioned, deterministic contracts for business-analysis evaluation."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal["completed", "partial", "failed", "insufficient_evidence"]
Split = Literal["development", "heldout"]


class EvaluationCase(BaseModel):
    """One immutable business outcome contract; no answer key is sent to the Agent."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    complexity: Literal["simple", "medium", "complex"]
    split: Split
    question: str = Field(min_length=1)
    company_scope: str = Field(min_length=1)
    document_scope: list[str] = Field(default_factory=list)
    expected_route: Literal["data_only", "knowledge_only", "hybrid"]
    expected_entities: list[str] = Field(min_length=1)
    expected_period: str = Field(min_length=1)
    expected_query_requirements: list[str] = Field(min_length=1)
    expected_result_fingerprint: dict[str, Any] = Field(min_length=1)
    expected_confirmed_facts: list[str] = Field(default_factory=list)
    expected_supported_claims: list[str] = Field(default_factory=list)
    allowed_chunk_ids: list[int] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_outcome: Outcome
    expected_limitations: list[str] = Field(default_factory=list)
    max_model_calls: int = Field(ge=0)
    max_tokens: int = Field(ge=0)


class EvaluationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    dataset_version: str = Field(min_length=1)
    cases: list[EvaluationCase] = Field(min_length=1)


class EvaluationObservation(BaseModel):
    """Normalized, persisted output of one real Worker execution."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    actual_route: str | None = None
    actual_entities: list[str] = Field(default_factory=list)
    actual_period: str | None = None
    actual_result_fingerprint: dict[str, Any] | None = None
    actual_confirmed_facts: list[str] = Field(default_factory=list)
    actual_supported_claims: list[str] = Field(default_factory=list)
    returned_chunk_ids: list[int] = Field(default_factory=list)
    returned_document_paths: list[str] = Field(default_factory=list)
    actual_outcome: Outcome
    actual_limitations: list[str] = Field(default_factory=list)
    model_calls: int = Field(ge=0)
    tokens: int = Field(ge=0)
    report_persisted: bool
    numeric_checks_passed: bool
    deterministic_validation_passed: bool
    security_incidents: list[str] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, ge=0)
    cost: str | None = None


class EvaluationCaseResult(BaseModel):
    case_id: str
    passed: bool
    route_correct: bool
    entity_scope_correct: bool
    sql_result_equivalent: bool
    numeric_consistent: bool
    citation_scope_correct: bool
    required_facts_confirmed: bool
    required_claims_supported: bool
    forbidden_claim_free: bool
    outcome_correct: bool
    limitations_correct: bool
    within_budget: bool
    report_persisted: bool
    deterministic_validation_passed: bool
    security_gate_passed: bool
    violations: list[str] = Field(default_factory=list)


class EvaluationMetrics(BaseModel):
    cases: int
    trusted_business_analysis_success_rate: float
    route_accuracy: float
    sql_result_equivalence_rate: float
    numeric_consistency_rate: float
    citation_scope_correct_rate: float
    confirmed_fact_rate: float
    supported_claim_rate: float
    forbidden_claim_free_rate: float
    outcome_accuracy: float
    report_persisted_rate: float
    security_incident_count: int
    hard_gate_passed: bool
    duration_p95_ms: int | None
    model_calls: int
    tokens: int


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
    results: list[EvaluationCaseResult]
    metrics: EvaluationMetrics
