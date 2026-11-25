"""Data 节点：生成并执行查询。"""

from typing import Any

from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.data_agent import DataAgent
from app.modules.analysis.data.sql_tool import SQLTool
from app.modules.analysis.data.tool_agent import ToolCallingDataAgent
from app.modules.analysis.metrics.facts import (
    build_confirmed_facts,
    build_data_evidence,
)
from app.modules.runtime.model_governance import model_node_scope
from app.modules.runtime.tool_guard import (
    CircuitBreaker,
    GuardedTool,
    redis_breaker_store,
)
from app.modules.workflow.orchestration.node_outcome import NodeOutcome
from app.modules.workflow.orchestration.node_runner import NodeStep, run_node
from app.modules.workflow.orchestration.nodes._common import (
    _effective_question,
    model_tools_enabled,
)
from app.modules.workflow.orchestration.state import WorkflowState


def _data_node(state: WorkflowState) -> NodeStep:
    """
    Data 节点：执行 SQL 查询。

    “使用 resolved_question，否则回退原始问题”。和 state["user_id"]，
    DataAgent 根据 question 生成候选 SQL，随后自行校验并执行。
    写 state["data_result"]。
    """

    data_source = state.get("business_data_source")
    snapshot_data = state.get("schema_catalog")
    if data_source is not None and snapshot_data is not None:
        catalog = SnapshotCatalog.from_snapshot(snapshot_data)
        tool_runtime = state.get("tool_runtime")
        if tool_runtime is not None and model_tools_enabled(state.get("company_id")):
            sql_tool = SQLTool(data_source=data_source, snapshot_catalog=catalog)
            agent = ToolCallingDataAgent(
                sql_tool=tool_runtime.wrap(
                    GuardedTool(
                        sql_tool,
                        CircuitBreaker(
                            f"sql_query:{state.get('company_id')}",
                            redis_breaker_store(),
                        ),
                    )
                ),
                data_source=data_source,
                snapshot_catalog=catalog,
            )
        elif tool_runtime is not None:
            agent = DataAgent(
                sql_tool=tool_runtime.wrap(
                    SQLTool(data_source=data_source, snapshot_catalog=catalog)
                ),
                data_source=data_source,
                snapshot_catalog=catalog,
            )
        else:
            agent = DataAgent(data_source=data_source, snapshot_catalog=catalog)
    else:
        tool_runtime = state.get("tool_runtime")
        agent = (
            DataAgent(sql_tool=tool_runtime.wrap(SQLTool()))
            if tool_runtime is not None
            else DataAgent()
        )
    data_context = {}
    if state.get("routing_feedback") is not None:
        data_context["feedback"] = state["routing_feedback"]
    if state.get("retry_context") is not None:
        data_context["retry_context"] = state["retry_context"]
    if state.get("semantic_review_enabled"):
        data_context.update(
            {
                "plan": state.get("plan") or {},
                "semantic_review_enabled": True,
            }
        )
    is_repair = bool((state.get("routing_feedback") or {}).get("mode"))
    with model_node_scope("data", is_repair=is_repair):
        result = agent.run(
            AgentInput(
                question=_effective_question(state),
                user_id=state["user_id"],
                context=data_context,
            )
        )
    if result.success:
        update: dict[str, Any] = {
            "data_result": {
                "status": "ready",
                "evidence": result.evidence,
                "attempts": result.attempts,
            }
        }
        update["confirmed_facts"] = [
            fact.model_dump()
            for fact in build_confirmed_facts(
                build_data_evidence(update["data_result"])
            )
        ]
        update["data_outcome"] = NodeOutcome(
            status="succeeded",
            output=update["data_result"],
            checkpoint_patch={"stage": "querying_data"},
        ).model_dump()
        return NodeStep(
            next_node=(
                "knowledge_node"
                if (state.get("plan") or {}).get("route") == "hybrid"
                else "reviewer_node"
            ),
            update=update,
        )
    if result.error_code == "no_matching_records":
        data_result = {
            "status": "insufficient_evidence",
            "error": result.error or "没有匹配的经营记录。",
            "error_code": result.error_code,
            "attempts": result.attempts,
            "candidate": result.evidence[0] if result.evidence else None,
        }
        update = {
            "data_result": data_result,
            "data_outcome": NodeOutcome(
                status="no_matching_records",
                output=data_result,
                error_code=result.error_code,
                checkpoint_patch={"stage": "querying_data"},
            ).model_dump(),
        }
        return NodeStep(
            next_node=(
                "knowledge_node"
                if (state.get("plan") or {}).get("route") == "hybrid"
                else "reviewer_node"
            ),
            update=update,
        )
    if result.error_code in {
        "insufficient_schema",
        "sql_semantic_unsupported",
        "no_matching_records",
        "invalid_result_shape",
        "query_contract_missing",
        "query_contract_incomplete",
    }:
        data_result = {
            "status": "insufficient_evidence",
            "error": result.error or "当前契约快照不足以回答该问题。",
            "error_code": result.error_code,
            "attempts": result.attempts,
            "candidate": result.evidence[0] if result.evidence else None,
        }
        update = {
            "data_result": data_result,
            "data_outcome": NodeOutcome(
                status=(
                    "repairable_error"
                    if result.error_code
                    in {"sql_semantic_unsupported", "query_contract_incomplete"}
                    else "insufficient_evidence"
                ),
                output=data_result,
                error_code=result.error_code,
                retry_hint=(
                    "repair"
                    if result.error_code
                    in {"sql_semantic_unsupported", "query_contract_incomplete"}
                    else "stop"
                ),
                checkpoint_patch={"stage": "querying_data"},
            ).model_dump(),
        }
        return NodeStep(
            next_node=(
                "knowledge_node"
                if (state.get("plan") or {}).get("route") == "hybrid"
                else "reviewer_node"
            ),
            update=update,
        )
    error_code = result.error_code or "business_db_execution_failed"
    retryable = error_code in {
        "business_db_execution_failed",
        "sql_generation_retryable_error",
        "sql_generation_invalid_output",
        "data_attempt_budget_exhausted",
    }
    data_result = {
        "status": "failed",
        "error": result.error or "经营数据查询失败",
        "error_code": error_code,
        "attempts": result.attempts,
        "candidate": result.evidence[0] if result.evidence else None,
    }
    update = {
        "data_result": data_result,
        "data_outcome": NodeOutcome(
            status="retryable_error" if retryable else "denied",
            output=data_result,
            error_code=error_code,
            retry_hint="retry" if retryable else "stop",
            checkpoint_patch={"stage": "querying_data"},
        ).model_dump(),
        "error": result.error,
    }
    return NodeStep(
        next_node=(
            "knowledge_node"
            if (state.get("plan") or {}).get("route") == "hybrid"
            else "reviewer_node"
        ),
        update=update,
    )


data_node = run_node("data_node", "querying_data", _data_node)
