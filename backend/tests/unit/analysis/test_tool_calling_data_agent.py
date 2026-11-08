"""The model chooses tools, but every gate of the fixed route still decides."""

import json
from decimal import Decimal
from types import SimpleNamespace

from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_candidate import SQLCandidate
from app.modules.analysis.data.tool_agent import (
    ToolCallingDataAgent,
    build_data_tool_prompt,
    summarize_rows,
)
from app.modules.analysis.tool_protocol import Tool, ToolOutput
from app.modules.runtime.tool_loop import LoopLimits

CATALOG = SnapshotCatalog(
    tables={
        "sales_orders": frozenset({"id", "total_amount", "order_date", "status"}),
        "customers": frozenset({"id", "region_code"}),
    },
    joins=frozenset(),
)
CONTRACT = {
    "required_concepts": ["订单数"],
    "expected_columns": ["订单数"],
    "result_kind": "aggregate",
    "empty_result_policy": "no_matching_records",
}
SQL = 'SELECT COUNT(*) AS "订单数" FROM sales_orders'


def _run_sql(call_id="c1", sql=SQL, contract=None):
    return ToolChatResponse(
        None,
        (
            ToolCall(
                call_id,
                "run_sql",
                json.dumps(
                    {
                        "sql": sql,
                        "purpose": "统计订单",
                        "query_contract": contract or CONTRACT,
                    },
                    ensure_ascii=False,
                ),
            ),
        ),
    )


def _tool_call(name, arguments, call_id="c9"):
    return ToolChatResponse(
        None, (ToolCall(call_id, name, json.dumps(arguments, ensure_ascii=False)),)
    )


class _Scripted(ModelGateway):
    def __init__(self, responses, chat_output=None):
        self.responses = list(responses)
        self.chat_output = chat_output
        self.requests = []
        self.plain_calls = 0

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        self.plain_calls += 1
        return self.chat_output

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        self.requests.append(list(messages))
        return self.responses.pop(0)

    def count_tokens(self, text):
        return len(text)


class _SqlTool(Tool):
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.seen = []

    @property
    def name(self):
        return "sql_query"

    @property
    def description(self):
        return "sql"

    def execute(self, input):
        self.seen.append(input.parameters)
        return self.outputs.pop(0)


class _Reviewer:
    def __init__(self, decision="approve", reason="ok"):
        self.decision = decision
        self.reason = reason
        self.calls = 0

    def review_sql(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            decision=self.decision, reason=self.reason, missing_requirements=[]
        )


def _ok(rows=((Decimal(3),),)):
    return ToolOutput(success=True, data={"columns": ["订单数"], "rows": list(rows)})


def _agent(gateway, tool, reviewer=None, **kwargs):
    agent = ToolCallingDataAgent(
        gateway=gateway,
        sql_tool=tool,
        semantic_reviewer=reviewer or _Reviewer(),
        limits=LoopLimits(backoff_seconds=0),
        **kwargs,
    )
    agent._snapshot_catalog = CATALOG
    return agent


def _input(**context):
    return AgentInput(question="有多少订单", user_id=1, context=context)


def _tool_replies(gateway):
    return [
        json.loads(m["content"]) for m in gateway.requests[-1] if m["role"] == "tool"
    ]


def test_a_non_empty_result_finishes_and_keeps_the_fixed_output_shape():
    gateway = _Scripted([_run_sql()])
    output = _agent(gateway, _SqlTool([_ok()])).run(_input())
    assert output.success
    evidence = output.evidence[0]
    assert evidence["rows"] == [["3"]]
    assert {"sql", "purpose", "query_contract", "result_assessment"} <= set(evidence)
    assert output.attempts["tool_loop"]["stop_reason"] == "finished"
    assert output.attempts["sql_attempts"] == 1


def test_only_sql_reaches_the_tool_the_model_cannot_set_scope():
    tool = _SqlTool([_ok()])
    _agent(_Scripted([_run_sql()]), tool).run(_input())
    assert list(tool.seen[0]) == ["sql"]


def test_a_validation_error_goes_back_and_the_model_repairs_it():
    refused = ToolOutput(
        success=False,
        error="字段不存在：x",
        error_code="sql_validation_error",
        repairable=True,
    )
    gateway = _Scripted([_run_sql(), _run_sql("c2", sql=SQL + " WHERE 1=1")])
    output = _agent(gateway, _SqlTool([refused, _ok()])).run(_input())
    assert output.success
    assert _tool_replies(gateway)[0]["error"] == "字段不存在：x"
    assert output.attempts["sql_attempts"] == 2


def test_a_statement_the_database_rejects_goes_back_with_the_reason():
    rejected = ToolOutput(
        success=False,
        error="经营数据查询暂时无法完成。",
        error_code="business_db_execution_failed",
        model_feedback='invalid input syntax for type date: "2025-08"',
    )
    gateway = _Scripted([_run_sql(), _run_sql("c2", sql=SQL + " WHERE 1=1")])
    output = _agent(gateway, _SqlTool([rejected, _ok()])).run(_input())
    assert output.success
    assert "2025-08" in _tool_replies(gateway)[0]["error"]


def test_an_outage_stops_without_switching_because_the_database_is_the_same():
    down = ToolOutput(
        success=False,
        error="经营数据查询暂时无法完成。",
        error_code="business_db_execution_failed",
    )
    gateway = _Scripted([_run_sql()], chat_output="unused")
    output = _agent(gateway, _SqlTool([down])).run(_input())
    assert not output.success
    assert output.error_code == "business_db_execution_failed"
    assert gateway.plain_calls == 0


def test_a_denial_stops_at_once_and_does_not_switch_to_the_fixed_route():
    denied = ToolOutput(
        success=False, error="无权", error_code="tool_current_authorization_denied"
    )
    gateway = _Scripted([_run_sql()], chat_output="unused")
    output = _agent(gateway, _SqlTool([denied])).run(_input())
    assert not output.success
    assert output.error_code == "tool_current_authorization_denied"
    assert len(gateway.requests) == 1
    assert gateway.plain_calls == 0


def test_an_exhausted_budget_stops_and_keeps_its_code():
    exhausted = ToolOutput(
        success=False, error="用完", error_code="tool_budget_exhausted"
    )
    output = _agent(_Scripted([_run_sql()]), _SqlTool([exhausted])).run(_input())
    assert output.error_code == "tool_budget_exhausted"


def test_review_runs_and_a_refusal_never_reaches_the_tool():
    reviewer = _Reviewer(decision="repair", reason="聚合不对")
    tool = _SqlTool([])
    gateway = _Scripted([_run_sql(), ToolChatResponse("放弃")], chat_output="{}")
    agent = _agent(gateway, tool, reviewer=reviewer)
    agent._sql_generator = SimpleNamespace(
        generate=lambda *a, **k: SQLCandidate(sql=SQL, purpose="p")
    )
    agent.run(_input(semantic_review_enabled=True))
    assert reviewer.calls == 1
    assert tool.seen == []
    assert _tool_replies(gateway)[0]["error"] == "聚合不对"


def test_the_contract_must_cover_what_the_plan_requires():
    gateway = _Scripted([_run_sql(), _run_sql("c2")] + [_run_sql("c3")])
    plan = {"intent": {"required_capabilities": ["销售额"]}}
    tool = _SqlTool([])
    agent = _agent(gateway, tool)
    agent._sql_generator = SimpleNamespace(
        generate=lambda *a, **k: SQLCandidate(sql=SQL, purpose="p")
    )
    agent.run(_input(semantic_review_enabled=True, plan=plan))
    assert tool.seen == []
    assert _tool_replies(gateway)[0]["missing"] == ["销售额"]


def test_an_empty_result_is_shown_and_needs_the_model_to_confirm():
    gateway = _Scripted(
        [_run_sql(), _tool_call("submit_result", {"evidence_id": "E1"})]
    )
    empty = ToolOutput(success=True, data={"columns": ["订单数"], "rows": []})
    output = _agent(gateway, _SqlTool([empty])).run(_input())
    assert _tool_replies(gateway)[0]["total_rows"] == 0
    # Same outcome as the fixed route: routing has its own path for an empty result.
    assert not output.success
    assert output.error_code == "no_matching_records"
    assert output.evidence[0]["rows"] == []


def test_an_unknown_evidence_id_is_refused():
    gateway = _Scripted(
        [_tool_call("submit_result", {"evidence_id": "E9"}), ToolChatResponse("算了")]
    )
    agent = _agent(gateway, _SqlTool([_ok()]))
    agent._sql_generator = SimpleNamespace(
        generate=lambda *a, **k: SQLCandidate(sql=SQL, purpose="p")
    )
    output = agent.run(_input())
    assert output.attempts["switched_to_fixed"] == "answered_in_text"


def test_describe_returns_columns_and_refuses_tables_outside_the_snapshot():
    gateway = _Scripted(
        [
            _tool_call("describe_table", {"tables": ["sales_orders"]}, "a"),
            _tool_call("describe_table", {"tables": ["pg_user"]}, "b"),
            _run_sql(),
        ]
    )
    _agent(gateway, _SqlTool([_ok()])).run(_input())
    replies = _tool_replies(gateway)
    assert "total_amount" in replies[0]["sales_orders"]["columns"]
    assert replies[1]["unknown"] == ["pg_user"]


def test_report_insufficient_ends_as_a_failure_with_the_fixed_code():
    gateway = _Scripted([_tool_call("report_insufficient", {"reason": "没有满意度表"})])
    output = _agent(gateway, _SqlTool([])).run(_input())
    assert not output.success
    assert output.error_code == "insufficient_schema"


def test_losing_its_way_switches_to_the_fixed_route():
    gateway = _Scripted([ToolChatResponse("我不知道")])
    tool = _SqlTool([_ok()])
    agent = _agent(gateway, tool)
    agent._sql_generator = SimpleNamespace(
        generate=lambda *a, **k: SQLCandidate(sql=SQL, purpose="统计订单")
    )
    output = agent.run(_input())
    assert output.success
    assert output.attempts["switched_to_fixed"] == "answered_in_text"
    assert "tool_loop" in output.attempts


def test_feedback_from_routing_uses_the_fixed_route():
    tool = _SqlTool([_ok()])
    gateway = _Scripted([])
    agent = _agent(gateway, tool)
    output = agent.run(
        _input(
            feedback={
                "target": "data",
                "mode": "replay_validated_sql",
                "previous_sql": SQL,
                "query_contract": CONTRACT,
            }
        )
    )
    assert output.success
    assert gateway.requests == []


def test_the_model_sees_a_trim_but_the_evidence_keeps_every_row():
    rows = [(Decimal(i),) for i in range(20)]
    summary = summarize_rows(["订单数"], rows)
    assert len(summary["rows"]) == 5
    assert summary["total_rows"] == 20
    assert summary["truncated"] is True
    assert summary["statistics"]["订单数"]["sum"] == "190"
    output = _agent(_Scripted([_run_sql()]), _SqlTool([_ok(rows)])).run(_input())
    assert len(output.evidence[0]["rows"]) == 20


def test_the_prompt_gives_names_and_metrics_but_columns_only_when_seeded():
    bare = build_data_tool_prompt(CATALOG)
    assert "sales_orders" in bare
    assert "region_code" not in bare
    seeded = build_data_tool_prompt(CATALOG, seeded={"customers"})
    assert "region_code" in seeded
