"""Fault drill for model-chosen tools: does each protection really trigger?

The faults are real where it matters: the circuit runs on the real Redis and the
outage is a real refused connection.  The model is scripted, so the drill costs
nothing and always asks for the same thing.  Expected actions come from
``fault_cases`` in tool_selection_extra_v1.json, written before this drill existed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.sql_candidate import SQLCandidate
from app.modules.analysis.data.tool_agent import ToolCallingDataAgent
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.knowledge.tool_agent import ToolCallingKnowledgeAgent
from app.modules.runtime.tool_guard import (
    CIRCUIT_OPEN_CODE,
    CircuitBreaker,
    FallbackTool,
    GuardedTool,
    redis_breaker_store,
)
from app.modules.runtime.tool_loop import LoopLimits

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests/fixtures/evaluation_tools/tool_selection_extra_v1.json"
)
CATALOG = SnapshotCatalog(
    tables={"sales_orders": frozenset({"id", "total_amount", "status"})},
    joins=frozenset(),
)
CONTRACT = {
    "required_concepts": ["订单数"],
    "expected_columns": ["订单数"],
    "result_kind": "aggregate",
    "empty_result_policy": "no_matching_records",
}
SQL = 'SELECT COUNT(*) AS "订单数" FROM sales_orders'
ROWS = {"columns": ["订单数"], "rows": [(3,)]}


class Scripted(ModelGateway):
    def __init__(self, responses=(), chat_output="{}"):
        self.responses = list(responses)
        self.chat_output = chat_output
        self.tool_rounds = 0

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        return self.chat_output

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        self.tool_rounds += 1
        return self.responses.pop(0)

    def count_tokens(self, text):
        return len(text)


class Faulty(Tool):
    """Plays back outputs; the last one repeats, and every call is counted."""

    def __init__(self, *outputs, name="sql_query"):
        self.outputs = list(outputs)
        self.calls = 0
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return "drill"

    def execute(self, input):
        self.calls += 1
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


def _run_sql(call_id="c1", sql=SQL):
    arguments = {"sql": sql, "purpose": "统计订单", "query_contract": CONTRACT}
    return ToolChatResponse(
        None, (ToolCall(call_id, "run_sql", json.dumps(arguments, ensure_ascii=False)),)
    )


def _data_agent(gateway, tool, generator_sql=SQL):
    agent = ToolCallingDataAgent(
        gateway=gateway,
        sql_tool=tool,
        semantic_reviewer=SimpleNamespace(),
        limits=LoopLimits(backoff_seconds=0),
    )
    agent._snapshot_catalog = CATALOG
    agent._sql_generator = SimpleNamespace(
        generate=lambda *a, **k: SQLCandidate(sql=generator_sql, purpose="统计订单")
    )
    return agent


def _question():
    return AgentInput(question="有多少订单", user_id=1, context={})


def _breaker(store, **kwargs):
    return CircuitBreaker(
        f"drill:{uuid4().hex}",
        store,
        **{"threshold": 3, "cooldown_seconds": 2, "probe_seconds": 5, **kwargs},
    )


def drill_sql_syntax(_store):
    refused = ToolOutput(
        success=False,
        error="字段不存在：x",
        error_code="sql_validation_error",
        repairable=True,
    )
    gateway = Scripted([_run_sql(), _run_sql("c2", SQL + " WHERE 1=1")])
    output = _data_agent(gateway, Faulty(refused, ToolOutput(True, ROWS))).run(
        _question()
    )
    return {
        "action": "repair_with_reason" if output.success else "none",
        "sql_attempts": output.attempts["sql_attempts"],
    }


def drill_sql_permission(_store):
    denied = ToolOutput(
        success=False, error="无权", error_code="tool_company_scope_denied"
    )
    gateway = Scripted([_run_sql(), _run_sql("c2")])
    tool = Faulty(denied)
    output = _data_agent(gateway, tool).run(_question())
    return {
        "action": "stop" if tool.calls == 1 and gateway.tool_rounds == 1 else "none",
        "error_code": output.error_code,
    }


def drill_sql_timeout(_store):
    timeout = ToolOutput(
        success=False,
        error="经营数据查询超时。",
        error_code="sql_statement_timeout",
        repairable=True,
    )
    gateway = Scripted([_run_sql(), _run_sql("c2", SQL + " WHERE 1=1")])
    output = _data_agent(gateway, Faulty(timeout, ToolOutput(True, ROWS))).run(
        _question()
    )
    return {"action": "repair_with_reason" if output.success else "none"}


def drill_sql_repeat(_store):
    refused = ToolOutput(
        success=False,
        error="字段不存在：x",
        error_code="sql_validation_error",
        repairable=True,
    )
    gateway = Scripted([_run_sql(), _run_sql("c2")])
    tool = Faulty(refused, refused, ToolOutput(True, ROWS))
    output = _data_agent(gateway, tool).run(_question())
    switched = output.attempts.get("switched_to_fixed")
    return {
        "action": "switch_or_partial" if switched == "no_progress" else "none",
        "fixed_route_success": output.success,
    }


def drill_rag_mcp_down(store):
    """A real circuit around an MCP tool that cannot connect."""
    from app.modules.knowledge.mcp_adapter import (
        MCP_RUNTIME_CONTEXT_VERSION,
        MCP_TOOL_CONTRACT_VERSION,
        McpEvidenceReadTool,
        document_scope_sha256,
    )
    from mcp import StdioServerParameters

    context = {
        "version": MCP_RUNTIME_CONTEXT_VERSION,
        "tool_contract_version": MCP_TOOL_CONTRACT_VERSION,
        "task_id": 1,
        "execution_id": "drill",
        "actor_id": 1,
        "actor_auth_version": 1,
        "authorized_role": "analyst",
        "company_id": 1,
        "document_scope_sha256": document_scope_sha256(1, [1]),
    }

    class WithRuntimeContext(Tool):
        """What ToolRuntime attaches before a request crosses to MCP."""

        def __init__(self, tool):
            self._tool = tool

        @property
        def name(self):
            return self._tool.name

        @property
        def description(self):
            return self._tool.description

        def execute(self, input):
            return self._tool.execute(
                ToolInput(
                    parameters={**input.parameters, "_runtime_mcp_context": context}
                )
            )

    unreachable = McpEvidenceReadTool(
        StdioServerParameters(command="definitely-not-a-real-mcp-server")
    )
    answer = json.dumps(
        {"answer": "主管审批", "citations": [{"chunk_id": 7}]}, ensure_ascii=False
    )
    local = Faulty(
        ToolOutput(
            True,
            {
                "status": "ready",
                "evidences": [
                    {
                        "chunk_id": 7,
                        "document_id": 1,
                        "content": "退货需要主管审批。",
                        "score": 0.9,
                    }
                ],
            },
        ),
        name="rag_search",
    )
    tool = FallbackTool(
        GuardedTool(unreachable, _breaker(store), retries=0, sleep=lambda _s: None),
        local,
    )
    gateway = Scripted(
        [ToolChatResponse(None, (ToolCall("c1", "submit_answer", answer),))]
    )
    question = AgentInput(
        question="退货流程",
        user_id=1,
        context={"company_id": 1, "document_ids": [1]},
    )
    # Without the authorization context it is a refusal, and a refusal never switches.
    unauthorized = tool.execute(
        ToolInput(parameters={"company_id": 1, "document_ids": [1], "question": "q"})
    )
    refused_without_switch = (
        unauthorized.error_code == "mcp_runtime_context_invalid" and local.calls == 0
    )
    output = ToolCallingKnowledgeAgent(
        rag_tool=WithRuntimeContext(tool), gateway=gateway
    ).run(question)
    return {
        "action": "switch_tool"
        if output.attempts.get("switched_from")
        and local.calls == 1
        and refused_without_switch
        else "none",
        "switched_from": output.attempts.get("switched_from"),
        "answer_kept": output.success and bool(output.evidence),
        "refused_without_switch": refused_without_switch,
    }


def drill_rerank_timeout(_store):
    from unittest import mock

    from app.modules.knowledge import tool as tool_module
    from app.modules.knowledge.tool import RAGTool

    def evidence(chunk_id):
        return SimpleNamespace(
            chunk_id=chunk_id,
            document_id=1,
            content=f"内容{chunk_id}",
            document_name="制度",
            document_type="txt",
            page_number=1,
            paragraph_start=1,
            paragraph_end=1,
            score=0.8,
            rerank_score=None,
            chunk_strategy="s",
            retrieval_strategies=("vector",),
            effective_from=None,
            effective_to=None,
            applies_to=None,
        )

    class Db:
        def execute(self, *_a, **_k):
            return None

        def close(self):
            pass

    def boom(*_a, **_k):
        raise TimeoutError("reranker timed out")

    with (
        mock.patch.object(tool_module, "SessionLocal", Db),
        mock.patch.object(tool_module, "set_tenant_scope", lambda *_: None),
        mock.patch.object(tool_module, "LocalEmbeddingProvider", lambda: None),
        mock.patch.object(
            tool_module, "retrieve_evidence", lambda **_: [evidence(1), evidence(2)]
        ),
        mock.patch.object(tool_module, "reserve_local_resource_call", lambda **_: None),
        mock.patch.object(tool_module, "record_model_call", lambda *_a, **_k: None),
        mock.patch.object(tool_module, "rerank_evidences", boom),
    ):
        output = RAGTool(reranker=object(), degrade_on_rerank_failure=True).execute(
            ToolInput(parameters={"question": "退货流程审批", "company_id": 1})
        )
    return {
        "action": "degrade"
        if output.success and output.data.get("degraded")
        else "none"
    }


def drill_circuit_open(store):
    """Real Redis, a real refused connection, and a real recovery."""
    import time

    import psycopg
    from app.modules.analysis.data.sql_tool import SQLTool

    class RealOutage(Tool):
        """SQLTool's classification over a connection nothing listens on."""

        def __init__(self):
            self.calls = 0
            self.healthy = False

        @property
        def name(self):
            return "sql_query"

        @property
        def description(self):
            return "drill"

        def execute(self, input):
            self.calls += 1
            if self.healthy:
                return ToolOutput(True, ROWS)
            try:
                psycopg.connect(host="127.0.0.1", port=1, dbname="x", connect_timeout=1)
            except psycopg.OperationalError:
                pass
            return ToolOutput(
                success=False,
                error="经营数据查询暂时无法完成。",
                error_code="business_db_execution_failed",
            )

    assert SQLTool  # The code above must stay the one SQLTool returns for an outage.
    inner = RealOutage()
    guarded = GuardedTool(inner, _breaker(store), retries=0, sleep=lambda _s: None)
    probe = ToolInput(parameters={"sql": SQL})
    for _ in range(3):
        guarded.execute(probe)
    calls_when_open = inner.calls
    rejected = guarded.execute(probe)
    time.sleep(2.2)
    inner.healthy = True
    recovered = guarded.execute(probe)
    after = guarded.execute(probe)
    return {
        "action": "circuit_open"
        if rejected.error_code == CIRCUIT_OPEN_CODE
        and inner.calls == calls_when_open + 2
        and recovered.success
        and after.success
        else "none",
        "rejected_code": rejected.error_code,
        "probe_recovered": recovered.success,
    }


def drill_budget_exhausted(_store):
    exhausted = ToolOutput(
        success=False, error="用完", error_code="tool_budget_exhausted"
    )
    gateway = Scripted([_run_sql(), _run_sql("c2")])
    output = _data_agent(gateway, Faulty(exhausted)).run(_question())
    return {
        # Partial is decided downstream: Data reports the failure and stops asking.
        "action": "partial"
        if output.error_code == "tool_budget_exhausted" and gateway.tool_rounds == 1
        else "none",
        "error_code": output.error_code,
    }


DRILLS = {
    "fault-sql-syntax": drill_sql_syntax,
    "fault-sql-permission": drill_sql_permission,
    "fault-sql-timeout": drill_sql_timeout,
    "fault-sql-repeat": drill_sql_repeat,
    "fault-rag-mcp-down": drill_rag_mcp_down,
    "fault-rerank-timeout": drill_rerank_timeout,
    "fault-circuit-open": drill_circuit_open,
    "fault-budget-exhausted": drill_budget_exhausted,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    store = redis_breaker_store()
    store.ping()
    rows = []
    for case in json.loads(FIXTURE.read_text(encoding="utf-8"))["fault_cases"]:
        try:
            observed = DRILLS[case["case_id"]](store)
        except Exception as exc:  # noqa: BLE001 - A drill that crashes has failed.
            observed = {"action": "crashed", "error": type(exc).__name__}
        rows.append(
            {
                "case_id": case["case_id"],
                "expected": case["expected_action"],
                "passed": observed["action"] == case["expected_action"],
                **observed,
            }
        )
    report = {
        "cases": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "results": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    sys.exit(0 if report["passed"] == report["cases"] else 1)


if __name__ == "__main__":
    main()
