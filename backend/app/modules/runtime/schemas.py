"""Frozen, machine-enforced contracts for workflow tool access."""

from app.modules.analysis.data_request import DataRequest
from pydantic import BaseModel, Field, field_validator


class RAGSearchInputSchema(BaseModel):
    company_id: int
    document_ids: list[int] | None = None
    question: str = Field(min_length=1)


class SQLQueryInputSchema(BaseModel):
    sql: str = Field(min_length=1)


class TemplateQueryInputSchema(DataRequest):
    """Runtime contract for the registered-query tool."""


class ToolPolicy(BaseModel):
    """The allowlist and scope rules frozen when an analysis task is created."""

    allowed_tools: tuple[str, ...] = ("rag_search", "sql_query", "template_query")
    require_company_scope: bool = True
    require_frozen_document_scope: bool = True
    sql_statement_timeout_ms: int = Field(default=10_000, ge=100, le=60_000)
    rag_database_timeout_ms: int = Field(default=10_000, ge=100, le=60_000)

    @field_validator("allowed_tools")
    @classmethod
    def no_empty_or_duplicate_tool_names(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        if (
            not value
            or any(not name.strip() for name in value)
            or len(set(value)) != len(value)
        ):
            raise ValueError("tool policy requires unique non-empty tool names")
        return value


class ToolBudget(BaseModel):
    """Bound each task before a Tool is invoked, rather than after damage is done."""

    max_calls: int = Field(default=12, ge=1)
    max_calls_per_tool: int = Field(default=6, ge=1)


class ToolBudgetUsage(BaseModel):
    calls: int = Field(default=0, ge=0)
    calls_by_tool: dict[str, int] = Field(default_factory=dict)
