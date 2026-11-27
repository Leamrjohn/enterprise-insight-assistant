"""T1: the only place a tool is declared."""

from app.modules.runtime.schemas import (
    DataFreshnessInputSchema,
    DimensionListInputSchema,
    MetricLookupInputSchema,
    RAGSearchInputSchema,
    SQLQueryInputSchema,
    TemplateQueryInputSchema,
)
from app.modules.runtime.tools.definition import ModelText, ToolDefinition
from app.modules.runtime.tools.evidence import (
    DataFreshnessOutput,
    DimensionListOutput,
    MetricLookupOutput,
    RAGSearchOutput,
    SQLQueryOutput,
    TemplateQueryOutput,
    lookup_evidence,
    rag_search_evidence,
    sql_query_evidence,
    template_query_evidence,
)

ANALYSIS_ROLES = frozenset({"owner", "admin", "analyst"})

TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="rag_search",
        contract_version="rag_search/v2",
        input_model=RAGSearchInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        transport="mcp",
        output_model=RAGSearchOutput,
        to_evidence=rag_search_evidence,
    ),
    ToolDefinition(
        name="sql_query",
        contract_version="sql_query/v1",
        input_model=SQLQueryInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        transport="mcp",
        output_model=SQLQueryOutput,
        to_evidence=sql_query_evidence,
    ),
    ToolDefinition(
        name="template_query",
        contract_version="template_query/v1",
        input_model=TemplateQueryInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        transport="mcp",
        output_model=TemplateQueryOutput,
        to_evidence=template_query_evidence,
    ),
    # T11a: lookups with model_text; the data model calls them itself.
    ToolDefinition(
        name="metric_lookup",
        contract_version="metric_lookup/v1",
        input_model=MetricLookupInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        transport="mcp",
        output_model=MetricLookupOutput,
        to_evidence=lookup_evidence,
        model_text=ModelText(
            purpose="查一个指标的完整口径：编号、单位、聚合、时间列、固定筛选、保留小数位。",
            when_to_use="不确定问题里的指标对应哪个编号或口径时。",
            when_not_to_use="系统说明里已列出该指标且口径清楚时。",
            example={"name": "销售额"},
            common_errors=("传入表名或列名，而不是指标名",),
        ),
    ),
    ToolDefinition(
        name="dimension_list",
        contract_version="dimension_list/v1",
        input_model=DimensionListInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        transport="mcp",
        output_model=DimensionListOutput,
        to_evidence=lookup_evidence,
        model_text=ModelText(
            purpose="列出本公司数据里一个筛选字段实际出现的取值和中文含义，最多 50 个。",
            when_to_use="要按地区、客户等级、状态等筛选，但不确定库里怎么写时。",
            when_not_to_use="取值已经确定时；不要用它查明细数据。",
            example={"field": "customers.region_code"},
            common_errors=("只写列名不写表名",),
        ),
    ),
    ToolDefinition(
        name="data_freshness",
        contract_version="data_freshness/v1",
        input_model=DataFreshnessInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        transport="mcp",
        output_model=DataFreshnessOutput,
        to_evidence=lookup_evidence,
        model_text=ModelText(
            purpose="查指标数据覆盖的最早和最晚日期。",
            when_to_use="问题说“最近”“本月”“今年”等相对时间，需要知道数据到哪天时。",
            when_not_to_use="问题已给出明确日期范围时。",
            example={"metric": "销售额"},
            common_errors=("以为数据一定截止到今天",),
        ),
    ),
)
