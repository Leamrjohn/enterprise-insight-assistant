"""Contracts that separate a query executing from it proving an answer."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ClarificationSlot = Literal[
    "metric",
    "time_range",
    "comparison_period",
    "region",
    "customer",
    "product",
    "object",
]


class ClarificationSpec(BaseModel):
    """Machine-readable missing information; the UI text is rendered from it."""

    missing_slots: list[ClarificationSlot] = Field(min_length=1, max_length=3)
    examples: list[str] = Field(default_factory=list, max_length=3)


class QuestionIntent(BaseModel):
    """The business meaning the planner believes must be evidenced."""

    kind: Literal[
        "business_metric",
        "business_comparison",
        "business_cause",
        "document_question",
    ]
    required_capabilities: list[str] = Field(min_length=1, max_length=8)
    specified_slots: list[str] = Field(default_factory=list, max_length=8)


class QueryContract(BaseModel):
    """What one candidate query must return before it may become business evidence."""

    required_concepts: list[str] = Field(min_length=1, max_length=8)
    expected_columns: list[str] = Field(min_length=1, max_length=12)
    result_kind: Literal["aggregate", "records", "comparison"]
    empty_result_policy: Literal["no_matching_records"] = "no_matching_records"
    metric_definition_ref: str | None = Field(default=None, max_length=80)
    time_scope_column: str | None = Field(default=None, max_length=160)
    numeric_assertion: "NumericAssertion | None" = None


class NumericAssertion(BaseModel):
    """A bounded, machine-checkable numeric statement about one query result."""

    column: str = Field(min_length=1, max_length=160)
    operator: Literal["equals", "greater_than", "less_than"]
    value: Decimal


class QueryResultAssessment(BaseModel):
    """A deterministic post-execution assessment, never a model-generated conclusion."""

    status: Literal["supported", "no_matching_records", "invalid_result_shape"]
    reason: str
