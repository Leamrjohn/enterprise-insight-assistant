"""Frozen, deterministic admission checks for a business-evaluation run."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Literal

from app.modules.evaluation.business_schemas import (
    EvaluationCase,
    EvaluationMetrics,
    EvaluationObservation,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EvaluationThresholdContract(BaseModel):
    """Thresholds that must be fixed before collecting the selected run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["p0-evaluation-thresholds-v1", "p0-evaluation-thresholds-v2"]
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_split: Literal["development", "heldout"]
    expected_case_count: int = Field(gt=0)
    max_total_settled_cost_usd: Decimal = Field(gt=0)
    max_duration_p95_ms: int | None = Field(default=None, gt=0)
    baseline_run_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    max_duration_p95_multiplier: Decimal | None = Field(default=None, gt=0)
    max_machine_execution_duration_p95_multiplier: Decimal | None = Field(
        default=None, gt=0
    )
    max_cost_per_trusted_success_multiplier: Decimal | None = Field(
        default=None, gt=0
    )
    require_persisted_task_observations: bool = True
    require_hard_gate_passed: bool = True
    require_settled_cost: bool = True

    @field_validator("fixture_sha256")
    @classmethod
    def fixture_sha256_is_lowercase(cls, value: str) -> str:
        if value != value.lower():
            raise ValueError("fixture_sha256 must be lowercase")
        return value

    @model_validator(mode="after")
    def baseline_comparison_is_complete(self) -> EvaluationThresholdContract:
        duration_multiplier = (
            self.max_duration_p95_multiplier
            if self.schema_version == "p0-evaluation-thresholds-v1"
            else self.max_machine_execution_duration_p95_multiplier
        )
        values = (
            self.baseline_run_sha256,
            duration_multiplier,
            self.max_cost_per_trusted_success_multiplier,
        )
        if any(value is not None for value in values) and any(
            value is None for value in values
        ):
            raise ValueError(
                "baseline hash and both relative comparison multipliers are required together"
            )
        if self.schema_version == "p0-evaluation-thresholds-v1":
            if self.max_machine_execution_duration_p95_multiplier is not None:
                raise ValueError("v1 does not support machine execution duration thresholds")
        elif self.max_duration_p95_ms is not None or self.max_duration_p95_multiplier is not None:
            raise ValueError("v2 compares machine execution duration, not end-to-end duration")
        return self


def evaluate_threshold_contract(
    contract: EvaluationThresholdContract,
    *,
    fixture_bytes: bytes,
    cases: list[EvaluationCase],
    observations: list[EvaluationObservation],
    metrics: EvaluationMetrics,
    baseline_metrics: EvaluationMetrics | None = None,
    baseline_run_sha256: str | None = None,
) -> list[str]:
    """Return deterministic violations; an empty list is the only pass state."""

    violations: list[str] = []
    if hashlib.sha256(fixture_bytes).hexdigest() != contract.fixture_sha256:
        violations.append("fixture_sha256")
    if len(cases) != contract.expected_case_count:
        violations.append("expected_case_count")
    if any(case.split != contract.required_split for case in cases):
        violations.append("required_split")
    if contract.require_persisted_task_observations and any(
        observation.source != "persisted_task" for observation in observations
    ):
        violations.append("persisted_task_observation")
    observations_by_case_id = {observation.case_id: observation for observation in observations}
    if any(
        (observation := observations_by_case_id.get(case.case_id)) is not None
        and observation.model_calls > case.max_model_calls
        for case in cases
    ):
        violations.append("max_model_calls")
    if any(
        (observation := observations_by_case_id.get(case.case_id)) is not None
        and observation.tokens > case.max_tokens
        for case in cases
    ):
        violations.append("max_tokens")
    if contract.require_hard_gate_passed and not metrics.hard_gate_passed:
        violations.append("hard_gate_passed")
    if contract.require_settled_cost and (
        metrics.cost_status != "passed" or metrics.settled_cost is None
    ):
        violations.append("settled_cost")
    elif metrics.settled_cost is not None and Decimal(metrics.settled_cost) > contract.max_total_settled_cost_usd:
        violations.append("max_total_settled_cost_usd")
    if (
        contract.max_duration_p95_ms is not None
        and (
            metrics.duration_p95_ms is None
            or metrics.duration_p95_ms > contract.max_duration_p95_ms
        )
    ):
        violations.append("max_duration_p95_ms")
    if contract.baseline_run_sha256 is not None:
        if baseline_run_sha256 != contract.baseline_run_sha256:
            violations.append("baseline_run_sha256")
        elif baseline_metrics is None:
            violations.append("baseline_metrics")
        else:
            if contract.schema_version == "p0-evaluation-thresholds-v1":
                baseline_duration = baseline_metrics.duration_p95_ms
                candidate_duration = metrics.duration_p95_ms
                duration_multiplier = contract.max_duration_p95_multiplier
                duration_violation = "duration_p95_multiplier"
            else:
                baseline_duration = baseline_metrics.machine_execution_duration_p95_ms
                candidate_duration = metrics.machine_execution_duration_p95_ms
                duration_multiplier = (
                    contract.max_machine_execution_duration_p95_multiplier
                )
                duration_violation = "machine_execution_duration_p95_multiplier"
            if (
                baseline_duration is None
                or candidate_duration is None
                or duration_multiplier is None
                or candidate_duration > Decimal(baseline_duration) * duration_multiplier
            ):
                violations.append(duration_violation)
            if (
                baseline_metrics.cost_status != "passed"
                or baseline_metrics.settled_cost is None
                or baseline_metrics.success_count == 0
                or metrics.cost_status != "passed"
                or metrics.settled_cost is None
                or metrics.success_count == 0
                or Decimal(metrics.settled_cost) / metrics.success_count
                > Decimal(baseline_metrics.settled_cost)
                / baseline_metrics.success_count
                * contract.max_cost_per_trusted_success_multiplier
            ):
                violations.append("cost_per_trusted_success_multiplier")
    return violations
