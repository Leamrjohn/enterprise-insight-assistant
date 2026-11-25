import ast
from pathlib import Path

import pytest
from app.modules.analysis.data.sql_tool import SQLTool
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.tool import RAGTool
from app.modules.runtime.tool_guard import GuardedTool
from app.modules.runtime.tools import catalog
from app.modules.runtime.tools.definition import ToolDefinition
from app.modules.runtime.tools.registry import default_registry
from app.modules.workflow.orchestration import toolsets
from pydantic import BaseModel

MODULES = Path(__file__).resolve().parents[3] / "app" / "modules"
# T3b: nodes and agents receive tools; they never build one.
NO_TOOL_CONSTRUCTION = [
    *sorted((MODULES / "workflow" / "orchestration" / "nodes").glob("*.py")),
    MODULES / "analysis" / "data" / "data_agent.py",
    MODULES / "analysis" / "data" / "tool_agent.py",
    MODULES / "knowledge" / "agent.py",
    MODULES / "knowledge" / "tool_agent.py",
]
TOOL_CLASSES = {
    "SQLTool",
    "RAGTool",
    "TemplateQueryTool",
    "GuardedTool",
    "FallbackTool",
    "CircuitBreaker",
    "McpEvidenceReadTool",
}


def _constructed_tool_classes(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        owner = getattr(func, "value", None)
        if name in TOOL_CLASSES or getattr(owner, "id", "") in TOOL_CLASSES:
            found.append(f"{path.name}:{node.lineno} {name}")
    return found


def test_nodes_and_agents_never_build_a_tool():
    found = [
        item
        for path in NO_TOOL_CONSTRUCTION
        for item in _constructed_tool_classes(path)
    ]

    assert len(NO_TOOL_CONSTRUCTION) > 8  # the scan still sees the node package
    assert found == []


class _LookupInput(BaseModel):
    code: str


class _LookupOutput(BaseModel):
    name: str


class _LookupTool(Tool):
    """The 'implementation' edit: a new read-only tool."""

    @property
    def name(self) -> str:
        return "fake_lookup"

    @property
    def description(self) -> str:
        return "look up a product name"

    def execute(self, input: ToolInput) -> ToolOutput:
        return ToolOutput(
            success=True, data={"name": f"产品{input.parameters['code']}"}
        )


FAKE = ToolDefinition(
    name="fake_lookup",
    contract_version="fake_lookup/v1",
    input_model=_LookupInput,
    allowed_roles=catalog.ANALYSIS_ROLES,
    output_model=_LookupOutput,  # the 'result conversion' edit
    to_evidence=lambda output: [],
)


class _RecordingRuntime:
    def __init__(self) -> None:
        self.wrapped: list[str] = []

    def wrap(self, tool: Tool) -> Tool:
        self.wrapped.append(tool.name)
        return tool


@pytest.fixture
def no_breaker(monkeypatch):
    monkeypatch.setattr(toolsets, "redis_breaker_store", lambda: object())


def test_adding_a_tool_to_data_takes_four_edits_and_none_in_nodes(
    monkeypatch, no_breaker
):
    monkeypatch.setattr(catalog, "TOOLS", (*catalog.TOOLS, FAKE))  # 1. declare
    default_registry.cache_clear()
    monkeypatch.setitem(
        toolsets.TOOL_FACTORIES, "fake_lookup", lambda state: _LookupTool()
    )
    monkeypatch.setitem(  # 4. list it in the node's toolset
        toolsets.NODE_TOOLSETS, "data", (*toolsets.NODE_TOOLSETS["data"], "fake_lookup")
    )
    runtime = _RecordingRuntime()
    try:
        tools = toolsets.build_toolset("data", {"tool_runtime": runtime})  # type: ignore[typeddict-item]

        assert tools.names() == ("sql_query", "fake_lookup")
        assert runtime.wrapped == [
            "sql_query",
            "fake_lookup",
        ]  # both go through the gateway
        assert tools.call("fake_lookup", {"code": "A1"}).data == {"name": "产品A1"}
        assert default_registry().get("fake_lookup") is FAKE
    finally:
        default_registry.cache_clear()


def test_a_name_outside_the_node_toolset_is_refused():
    tools = toolsets.build_toolset("knowledge", {})  # type: ignore[typeddict-item]

    assert tools.names() == ("rag_search",)
    assert tools.call("sql_query", {"sql": "select 1"}).error_code == "tool_unknown"


def _built(node: str, state, monkeypatch, *, model_tools: bool) -> Tool:
    monkeypatch.setattr(toolsets, "model_tools_enabled", lambda company_id: model_tools)
    (tool,) = toolsets.build_toolset(node, state).tools()
    return tool


@pytest.mark.parametrize(
    ("node", "runtime", "model_tools", "expected"),
    [
        # Same objects the nodes built before T3b.
        ("data", False, False, SQLTool),
        ("data", True, False, SQLTool),
        ("knowledge", False, False, RAGTool),
        ("knowledge", True, False, RAGTool),
        ("knowledge", True, True, GuardedTool),
    ],
)
def test_each_route_gets_the_tool_it_had_before(
    node, runtime, model_tools, expected, monkeypatch, no_breaker
):
    state = {"tool_runtime": _RecordingRuntime()} if runtime else {}

    assert type(_built(node, state, monkeypatch, model_tools=model_tools)) is expected
