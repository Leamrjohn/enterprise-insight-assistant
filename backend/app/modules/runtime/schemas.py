"""Frozen, machine-enforced contracts for workflow tool access."""

from app.modules.analysis.data.data_request import DataRequest
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
)


class RAGSearchInputSchema(BaseModel):
    company_id: int
    document_ids: list[int] | None = None
    question: str = Field(min_length=1)
    # Set by code from the user's question; RAGTool defaults to "valid today" without it.
    validity_window: list[str] | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_window(self, handler):
        dumped = handler(self)
        if dumped.get("validity_window") is None:
            dumped.pop("validity_window", None)
        return dumped


class SQLQueryInputSchema(BaseModel):
    sql: str = Field(min_length=1)


class TemplateQueryInputSchema(DataRequest):
    """Runtime contract for the registered-query tool."""


# T11a: lookups the data model calls itself; the task's own source is implied.
class MetricLookupInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="指标中文名或编号，如 销售额、revenue/v1；不填返回全部指标",
    )


class DimensionListInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(
        min_length=3, max_length=80, description="表名.列名，如 customers.region_code"
    )


class DataFreshnessInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="指标中文名或编号；不填返回全部指标",
    )


def _registered_tool_names() -> tuple[str, ...]:
    # Imported here: the catalog itself imports the input schemas above.
    from app.modules.runtime.tools.registry import default_registry

    return default_registry().names()


class ToolPolicy(BaseModel):
    """The allowlist and scope rules frozen when an analysis task is created."""

    allowed_tools: tuple[str, ...] = Field(default_factory=_registered_tool_names)
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


class DocListInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocReadInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: int = Field(ge=1, description="doc_list 返回的文档编号")
    offset: int = Field(default=0, ge=0, description="从第几个字开始读，首次为 0")


# T11b: the second batch; a version, a memory or a report is named, never a scope.
class DocVersionDiffInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: int = Field(ge=1, description="较早版本的文档编号")
    other_document_id: int = Field(ge=1, description="较新版本的文档编号")


class MemorySearchInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=200, description="要找的结论关键词")


class ReportExportInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: int = Field(
        ge=1, description="报告所属任务编号，如 memory_search 的 source_task_id"
    )
