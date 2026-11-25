"""T1: the only place a tool is declared."""

from app.modules.runtime.schemas import (
    RAGSearchInputSchema,
    SQLQueryInputSchema,
    TemplateQueryInputSchema,
)
from app.modules.runtime.tools.definition import ToolDefinition
from app.modules.runtime.tools.evidence import (
    RAGSearchOutput,
    SQLQueryOutput,
    TemplateQueryOutput,
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
        output_model=RAGSearchOutput,
        to_evidence=rag_search_evidence,
    ),
    ToolDefinition(
        name="sql_query",
        contract_version="sql_query/v1",
        input_model=SQLQueryInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        output_model=SQLQueryOutput,
        to_evidence=sql_query_evidence,
    ),
    ToolDefinition(
        name="template_query",
        contract_version="template_query/v1",
        input_model=TemplateQueryInputSchema,
        allowed_roles=ANALYSIS_ROLES,
        output_model=TemplateQueryOutput,
        to_evidence=template_query_evidence,
    ),
)
