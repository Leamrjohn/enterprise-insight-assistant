"""T3b: which tools each node may use, and the only place tool objects are built.

Adding a read-only tool to a node takes four edits and none in nodes/ or the
agents: declare it in runtime/tools/catalog.py, implement it, give it an
output model and to_evidence, and list its name in NODE_TOOLSETS below with a
factory in TOOL_FACTORIES.  T11a: declared with model_text, the node's model
calls it by name (runtime/tools/direct.py); without, only the agent calls it.

T3b-2: the capability and control tools a model calls are declared next to the
agents that handle them; tool_catalog() puts them and the runtime tools into
one registry, so every declaration passes the same startup rules.
"""

from collections.abc import Callable, Mapping
from functools import lru_cache

from app.core.config.snapshot import runtime_settings
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_tool import SQLTool
from app.modules.analysis.data.tool_agent import DATA_TOOLS
from app.modules.analysis.tool_protocol import Tool, Toolset
from app.modules.knowledge.tool import RAGTool
from app.modules.knowledge.tool_agent import KNOWLEDGE_TOOLS
from app.modules.runtime.tool_guard import (
    CircuitBreaker,
    GuardedTool,
    redis_breaker_store,
)
from app.modules.runtime.tools import catalog
from app.modules.runtime.tools.registry import ToolRegistry
from app.modules.workflow.orchestration.state import WorkflowState

NODE_TOOLSETS: Mapping[str, tuple[str, ...]] = {
    "data": ("sql_query",),
    "knowledge": ("rag_search",),
}

ToolFactory = Callable[[WorkflowState], Tool]


def model_tools_enabled(company_id: int | None) -> bool:
    """Off by default; the allowlist lets one company try it before anyone else."""
    settings = runtime_settings()
    if settings.model_tool_mode == "all":
        return True
    return (
        settings.model_tool_mode == "allowlist"
        and company_id in settings.model_tool_company_ids
    )


def _sql_query(state: WorkflowState) -> Tool:
    data_source = state.get("business_data_source")
    snapshot_data = state.get("schema_catalog")
    if data_source is None or snapshot_data is None:
        return SQLTool()
    sql_tool = SQLTool(
        data_source=data_source,
        snapshot_catalog=SnapshotCatalog.from_snapshot(snapshot_data),
    )
    if state.get("tool_runtime") is None or not model_tools_enabled(
        state.get("company_id")
    ):
        return sql_tool
    # Only the model-chosen route is guarded; one company's outage opens only its circuit.
    return GuardedTool(
        sql_tool,
        CircuitBreaker(f"sql_query:{state.get('company_id')}", redis_breaker_store()),
    )


def _rag_search(state: WorkflowState) -> Tool:
    # M2b: with the tool service on, the runtime sends rag_search there and this
    # object only names the tool; with it off, the worker runs it in process.
    if state.get("tool_runtime") is None or not model_tools_enabled(
        state.get("company_id")
    ):
        return RAGTool()
    return GuardedTool(
        RAGTool(degrade_on_rerank_failure=True),
        CircuitBreaker("rag_search:local", redis_breaker_store()),
    )


TOOL_FACTORIES: Mapping[str, ToolFactory] = {
    "sql_query": _sql_query,
    "rag_search": _rag_search,
}


@lru_cache(maxsize=1)
def tool_catalog() -> ToolRegistry:
    """Every declared tool, runtime and model-facing alike; a bad one fails here."""
    return ToolRegistry((*catalog.TOOLS, *DATA_TOOLS, *KNOWLEDGE_TOOLS))


def build_toolset(node: str, state: WorkflowState) -> Toolset:
    """Build the node's tools; with a runtime, every call goes through its gateway."""
    tool_catalog()  # the first task refuses to run on a broken declaration
    runtime = state.get("tool_runtime")
    tools = [TOOL_FACTORIES[name](state) for name in NODE_TOOLSETS[node]]
    if runtime is not None:
        tools = [runtime.wrap(tool) for tool in tools]
    return Toolset.of(*tools)
