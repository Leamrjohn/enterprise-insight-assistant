"""T11a: a lookup declared with model_text reaches the model with no agent change."""

import json
from datetime import date
from decimal import Decimal

import pytest
from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.tool_agent import ToolCallingDataAgent
from app.modules.analysis.tool_protocol import Tool, ToolOutput, Toolset
from app.modules.runtime.tool_loop import LoopLimits, ToolReply
from app.modules.runtime.tools import catalog
from app.modules.runtime.tools.definition import ModelText, ToolDefinition
from app.modules.runtime.tools.direct import direct_tools, reply_for
from app.modules.runtime.tools.registry import default_registry, validate_definitions
from app.modules.workflow.orchestration.toolsets import tool_catalog
from pydantic import BaseModel, ConfigDict


class LookupArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str


class LookupOutput(BaseModel):
    name: str


FAKE = ToolDefinition(
    name="fake_lookup",
    contract_version="fake_lookup/v1",
    input_model=LookupArgs,
    allowed_roles=catalog.ANALYSIS_ROLES,
    output_model=LookupOutput,
    to_evidence=lambda output: [],
    model_text=ModelText(
        purpose="按编码查产品名称。",
        when_to_use="只知道产品编码时。",
        when_not_to_use="已知道名称时。",
        example={"code": "A1"},
    ),
)


class _Named(Tool):
    def __init__(self, name, outputs):
        self._name = name
        self.outputs = list(outputs)
        self.seen = []

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._name

    def execute(self, input):
        self.seen.append(input.parameters)
        return self.outputs.pop(0)


@pytest.fixture
def fake_declared(monkeypatch):
    monkeypatch.setattr(catalog, "TOOLS", (*catalog.TOOLS, FAKE))
    caches = (default_registry, tool_catalog)  # both read catalog.TOOLS once
    for cache in caches:
        cache.cache_clear()
    yield
    for cache in caches:
        cache.cache_clear()


# --- reply_for: the part written by hand -------------------------------------


def test_a_success_shows_the_data_as_plain_json():
    reply = reply_for(
        ToolOutput(
            success=True,
            data={"name": "产品A1", "price": Decimal("0.10"), "day": date(2026, 11, 1)},
        )
    )
    assert reply == ToolReply(
        {"result": {"name": "产品A1", "price": "0.10", "day": "2026-11-01"}}
    )
    json.dumps(reply.content, ensure_ascii=False)  # what tool_loop sends the model


def test_a_repairable_failure_shows_the_feedback_and_keeps_the_code():
    reply = reply_for(
        ToolOutput(
            success=False,
            error="编码不存在",
            error_code="tool_arguments_invalid",
            repairable=True,
            model_feedback="可用编码：A1、A2",
        )
    )
    assert reply == ToolReply(
        {"error": "可用编码：A1、A2"}, "repairable", "tool_arguments_invalid"
    )


def test_a_denial_stops_and_shows_only_the_error():
    reply = reply_for(
        ToolOutput(
            success=False,
            error="当前用户无权访问",
            error_code="tool_current_authorization_denied",
            model_feedback="不应展示",
        )
    )
    assert reply == ToolReply(
        {"error": "当前用户无权访问"}, "denied", "tool_current_authorization_denied"
    )


def test_an_outage_counts_as_unavailable():
    reply = reply_for(
        ToolOutput(
            success=False,
            error="工具服务不可用",
            error_code="mcp_transport_unavailable",
            repairable=True,
        )
    )
    assert reply == ToolReply(
        {"error": "工具服务不可用"}, "unavailable", "mcp_transport_unavailable"
    )


def test_a_failure_without_a_code_still_names_one():
    reply = reply_for(ToolOutput(success=False, error="失败"))
    assert reply.error_code == "tool_failed"


# --- wiring: done once, then never again --------------------------------------


def test_only_runtime_tools_with_model_text_are_offered(fake_declared):
    toolset = Toolset.of(_Named("sql_query", []), _Named("fake_lookup", []))
    specs, handlers = direct_tools(toolset)
    assert [spec.name for spec in specs] == ["fake_lookup"]
    assert set(handlers) == {"fake_lookup"}


def test_a_direct_tool_may_not_take_a_scope_field():
    class ScopedArgs(LookupArgs):
        company_id: int

    scoped = ToolDefinition(
        name="fake_lookup",
        contract_version="fake_lookup/v1",
        input_model=ScopedArgs,
        allowed_roles=catalog.ANALYSIS_ROLES,
        output_model=LookupOutput,
        to_evidence=lambda output: [],
        model_text=FAKE.model_text,
    )
    assert validate_definitions([scoped]) == [
        "fake_lookup: the model must not set company_id"
    ]


class _Scripted(ModelGateway):
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.offered = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        raise AssertionError("the tool loop never calls plain chat")

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        self.requests.append(list(messages))
        self.offered.append([tool["function"]["name"] for tool in tools])
        return self.responses.pop(0)

    def count_tokens(self, text):
        return len(text)


def _call(name, arguments, call_id):
    return ToolChatResponse(
        None, (ToolCall(call_id, name, json.dumps(arguments, ensure_ascii=False)),)
    )


def test_the_data_model_calls_a_listed_lookup_before_its_query(fake_declared):
    contract = {
        "required_concepts": ["订单数"],
        "expected_columns": ["订单数"],
        "result_kind": "aggregate",
        "empty_result_policy": "no_matching_records",
    }
    gateway = _Scripted(
        [
            _call("fake_lookup", {"code": "A1"}, "c1"),
            _call(
                "run_sql",
                {
                    "sql": 'SELECT COUNT(*) AS "订单数" FROM sales_orders',
                    "purpose": "统计订单",
                    "query_contract": contract,
                },
                "c2",
            ),
        ]
    )
    lookup = _Named("fake_lookup", [ToolOutput(success=True, data={"name": "产品A1"})])
    sql = _Named(
        "sql_query",
        [ToolOutput(success=True, data={"columns": ["订单数"], "rows": [[3]]})],
    )
    agent = ToolCallingDataAgent(
        gateway=gateway,
        tools=Toolset.of(sql, lookup),
        limits=LoopLimits(backoff_seconds=0),
    )
    agent._snapshot_catalog = SnapshotCatalog(
        tables={"sales_orders": frozenset({"id", "order_date"})}, joins=frozenset()
    )

    output = agent.run(AgentInput(question="A1 有多少订单", user_id=1, context={}))

    assert "fake_lookup" in gateway.offered[0]
    assert lookup.seen == [{"code": "A1"}]
    replies = [m for m in gateway.requests[1] if m["role"] == "tool"]
    assert json.loads(replies[0]["content"]) == {"result": {"name": "产品A1"}}
    assert output.success  # the evidence is the query's, not the lookup's
    assert [item["purpose"] for item in output.evidence] == ["统计订单"]
