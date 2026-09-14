"""LangGraph 工作流节点 —— 每个节点封装一个 Agent 调用"""

from typing import Any

from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.planner_agent import PlannerAgent
from app.modules.knowledge.agent import KnowledgeAgent
from app.modules.analysis.data_agent import DataAgent
from app.modules.reporting.reviewer_agent import ReviewerAgent
from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.modules.reporting.semantic_review_service import SemanticReviewService
from app.modules.reporting.citation_validation import validate_citations
from app.modules.workflow.state import WorkflowState
from app.modules.workflow.router import (
    MAX_EXTERNAL_RETRIES,
    build_feedback,
    build_scope_fingerprint,
    choose_next_action,
)
from app.modules.workflow.node_outcome import NodeOutcome
from app.modules.runtime.model_governance import model_node_scope
from app.modules.analysis.facts import build_confirmed_facts, build_data_evidence
from app.modules.analysis.snapshot_catalog import SnapshotCatalog
from app.modules.knowledge.tool import RAGTool
from app.modules.analysis.sql_tool import SQLTool


_CLARIFICATION_SLOT_LABELS = {
    "metric": "需要查询的经营指标",
    "time_range": "时间范围",
    "comparison_period": "对比时间范围",
    "region": "区域",
    "customer": "客户",
    "product": "产品",
    "object": "分析对象",
}


def _render_clarification(plan: dict) -> str:
    """Render a bounded user question from structured missing slots when present."""
    clarification = plan.get("clarification")
    if not isinstance(clarification, dict):
        return (
            plan.get("clarification_question")
            or "请补充需要分析的指标、时间、区域或对象。"
        )
    slots = clarification.get("missing_slots")
    if not isinstance(slots, list) or not slots:
        return (
            plan.get("clarification_question")
            or "请补充需要分析的指标、时间、区域或对象。"
        )
    labels = [_CLARIFICATION_SLOT_LABELS.get(slot, str(slot)) for slot in slots[:3]]
    examples = clarification.get("examples")
    example_text = ""
    if isinstance(examples, list) and examples:
        example_text = "，例如：" + "；".join(str(item) for item in examples[:3])
    return "请补充" + "、".join(labels) + example_text + "。"


def _set_stage(state: WorkflowState, stage: str) -> None:
    callback = state.get("stage_callback")
    if callback is not None:
        callback(stage)


def _checkpoint(
    state: WorkflowState,
    *,
    completed_node: str,
    next_node: str | None,
    update: dict,
) -> dict:
    """Persist a node's structured output after the node has completed."""
    callback = state.get("checkpoint_callback")
    if callback is not None:
        # Later nodes require earlier structured outputs too (for example,
        # Knowledge needs the already-approved Planner plan after Data was
        # completed).  Persist a small allow-listed cumulative snapshot rather
        # than the entire runtime state, which contains sessions and callbacks.
        snapshot_keys = (
            "plan",
            "planner_result",
            "planner_failure",
            "planner_outcome",
            "semantic_review_outcome",
            "data_result",
            "confirmed_facts",
            "knowledge_result",
            "data_outcome",
            "knowledge_outcome",
            "review_result",
            "reviewer_outcome",
            "terminal_result",
            "final_answer",
            "error",
            "scope_fingerprint",
            "external_retry_count",
            "routing_action",
            "routing_feedback",
            "loop_stop_reason",
            "loop_history",
            "cached_data_result",
            "cached_knowledge_result",
            "cache_scope_fingerprint",
            "empty_result_replanned",
        )
        snapshot = {
            key: update[key] if key in update else state.get(key)
            for key in snapshot_keys
            if (update[key] if key in update else state.get(key)) is not None
        }
        callback(completed_node, next_node, snapshot)
    return update


def _next_after_plan(plan: dict | None) -> str:
    if not isinstance(plan, dict):
        return "planning_failure_node"
    if plan.get("action") == "analyze":
        return (
            "data_node"
            if plan.get("route") in {"data_only", "hybrid"}
            else "knowledge_node"
        )
    return "planner_terminal_node"


def _effective_question(state: WorkflowState) -> str:
    """Use the Planner's standalone question without overwriting user input."""
    return (state.get("plan") or {}).get("resolved_question") or state["question"]


def planner_node(state: WorkflowState) -> dict:
    """
    Planner 节点：分析问题，输出计划。

    读 state["question"] 和 state["user_id"]，
    写 state["plan"]。
    """
    _set_stage(state, "planning")
    agent = PlannerAgent()
    with model_node_scope("planner"):
        result = agent.run(
            AgentInput(
                question=state["question"],
                user_id=state["user_id"],
                context={
                    "conversation_context": state.get("conversation_context"),
                    **(
                        {"planner_memory": state["planner_memory"]}
                        if state.get("planner_memory")
                        else {}
                    ),
                    **(
                        {"feedback": state["routing_feedback"]}
                        if state.get("routing_feedback") is not None
                        else {}
                    ),
                },
            )
        )
    if result.success and result.plan:
        update = {
            "plan": result.plan,
            "scope_fingerprint": build_scope_fingerprint(state, result.plan),
            "planner_result": {
                "status": "ready",
                "attempts": result.attempts,
            },
            "planner_outcome": NodeOutcome(
                status="succeeded",
                output={"plan": result.plan},
                checkpoint_patch={"stage": "planning"},
            ).model_dump(),
        }
        return _checkpoint(
            state,
            completed_node="planner_node",
            next_node="planner_semantic_review_node",
            update=update,
        )
    update = {
        "error": result.error,
        "plan": None,
        "planner_result": {
            "status": "failed",
            "attempts": result.attempts,
        },
        "planner_failure": {
            "code": result.error_code or "planner_unknown_error",
            "message": result.error or "Planner 未能生成有效决策",
            "retryable": result.retryable,
        },
        "planner_outcome": NodeOutcome(
            status="retryable_error" if result.retryable else "repairable_error",
            output={},
            error_code=result.error_code or "planner_unknown_error",
            retry_hint="retry" if result.retryable else "repair",
            checkpoint_patch={"stage": "planning"},
        ).model_dump(),
    }
    return _checkpoint(
        state,
        completed_node="planner_node",
        next_node="planning_failure_node",
        update=update,
    )


def planner_semantic_review_node(state: WorkflowState) -> dict:
    """Let a second model pass check the Planner decision against the snapshot."""
    if not state.get("semantic_review_enabled"):
        return {}
    plan = state.get("plan")
    if not plan:
        return {}
    # The durable task stage remains "planning"; semantic review is a planning substep.
    _set_stage(state, "planning")
    catalog_data = state.get("schema_catalog")
    catalog = (
        SnapshotCatalog.from_snapshot(catalog_data)
        if isinstance(catalog_data, dict)
        else None
    )
    service = SemanticReviewService()
    try:
        with model_node_scope("semantic_review"):
            reviewed_plan = service.review_plan(
                question=state["question"],
                proposed_plan=plan,
                catalog=catalog,
            )
    except (PermanentModelError, RetryableModelError, StructuredOutputError) as error:
        update = {
            "plan": {
                "action": "needs_clarification",
                "route": None,
                "reason": "无法完成问题语义复核，未进入数据查询。",
                "clarification_question": "请稍后重试，或补充更明确的经营指标、范围和时间条件。",
                "response_message": None,
                "resolved_question": None,
                "clarification": {
                    "missing_slots": ["metric", "time_range"],
                    "examples": [],
                },
            },
            "planner_result": {
                "status": "semantic_review_failed",
                "attempts": {
                    **((state.get("planner_result") or {}).get("attempts") or {}),
                    "semantic_review_attempts": service.model_attempts,
                },
            },
            "error": f"Planner 语义复核失败: {error}",
            "semantic_review_outcome": NodeOutcome(
                status="retryable_error"
                if isinstance(error, RetryableModelError)
                else "repairable_error",
                output={},
                error_code="semantic_review_failed",
                retry_hint="retry"
                if isinstance(error, RetryableModelError)
                else "repair",
                checkpoint_patch={"stage": "planning"},
            ).model_dump(),
        }
        return _checkpoint(
            state,
            completed_node="planner_semantic_review_node",
            next_node="planner_terminal_node",
            update=update,
        )
    if reviewed_plan.action == "analyze" and reviewed_plan.intent is None:
        update = {
            "plan": {
                "action": "needs_clarification",
                "route": None,
                "reason": "规划结果未说明需要哪些业务证据，未进入数据查询。",
                "clarification_question": "请补充需要确认的经营指标、对象和时间范围。",
                "response_message": None,
                "resolved_question": None,
                "clarification": {
                    "missing_slots": ["metric", "time_range"],
                    "examples": [],
                },
                "intent": None,
            },
            "planner_result": {
                "status": "intent_contract_missing",
                "attempts": {
                    **((state.get("planner_result") or {}).get("attempts") or {}),
                    "semantic_review_attempts": service.model_attempts,
                },
            },
            "semantic_review_outcome": NodeOutcome(
                status="repairable_error",
                output={},
                error_code="planner_intent_contract_missing",
                retry_hint="repair",
                checkpoint_patch={"stage": "planning"},
            ).model_dump(),
        }
        return _checkpoint(
            state,
            completed_node="planner_semantic_review_node",
            next_node="planner_terminal_node",
            update=update,
        )
    update = {
        "plan": reviewed_plan.model_dump(),
        "scope_fingerprint": build_scope_fingerprint(state, reviewed_plan.model_dump()),
        "planner_result": {
            "status": "ready",
            "attempts": {
                **((state.get("planner_result") or {}).get("attempts") or {}),
                "semantic_review_attempts": service.model_attempts,
            },
        },
        "semantic_review_outcome": NodeOutcome(
            status="succeeded",
            output={"plan": reviewed_plan.model_dump()},
            checkpoint_patch={"stage": "planning"},
        ).model_dump(),
    }
    return _checkpoint(
        state,
        completed_node="planner_semantic_review_node",
        next_node=_next_after_plan(update["plan"]),
        update=update,
    )


def planner_terminal_node(state: WorkflowState) -> dict:
    """Return a deterministic terminal response for non-analysis Planner actions."""
    plan = state.get("plan") or {}
    action = plan.get("action")

    if action == "needs_clarification":
        answer = _render_clarification(plan)
    else:
        answer = plan.get("response_message") or "当前问题无法进入分析流程。"

    return {
        "terminal_result": {
            "outcome": action,
            "reason": plan.get("reason"),
        },
        "final_answer": answer,
    }


def planning_failure_node(state: WorkflowState) -> dict:
    """Stop safely when the Planner model call or JSON validation failed."""
    failure = state.get("planner_failure") or {}
    retryable = bool(failure.get("retryable"))
    message = failure.get("message") or "Planner 未能生成有效决策"
    answer = "本次分析暂未完成，请稍后重试。"

    return {
        "terminal_result": {
            "outcome": "failed",
            "stage": "planning",
            "error_code": failure.get("code") or "planner_unknown_error",
            "retryable": retryable,
        },
        "final_answer": answer,
        "error": message,
    }


def knowledge_node(state: WorkflowState) -> dict:
    """
    Knowledge 节点：检索文档证据。

    “使用 resolved_question，否则回退原始问题”和 state["user_id"]，
    写 state["knowledge_result"]。
    """
    _set_stage(state, "retrieving_knowledge")
    runtime = state.get("tool_runtime")
    agent = (
        KnowledgeAgent(rag_tool=runtime.wrap(RAGTool()))
        if runtime
        else KnowledgeAgent()
    )
    with model_node_scope("knowledge"):
        result = agent.run(
            AgentInput(
                question=_effective_question(state),
                user_id=state["user_id"],
                context={
                    "company_id": state.get("company_id"),
                    "confirmed_facts": state.get("confirmed_facts") or [],
                    **(
                        {"document_ids": state["document_ids"]}
                        if state.get("document_ids") is not None
                        else {}
                    ),
                    **(
                        {"feedback": state["routing_feedback"]}
                        if state.get("routing_feedback") is not None
                        else {}
                    ),
                },
            )
        )
    if result.success:
        knowledge_result = {
            "status": ("ready" if result.evidence else "insufficient_evidence"),
            "answer": result.answer,
            "evidences": result.evidence,
        }
        if result.error_code is not None:
            knowledge_result["error_code"] = result.error_code
        if result.attempts:
            knowledge_result["attempts"] = result.attempts
        update = {
            "knowledge_result": knowledge_result,
            "knowledge_outcome": NodeOutcome(
                status=("succeeded" if result.evidence else "insufficient_evidence"),
                output=knowledge_result,
                error_code=result.error_code,
                checkpoint_patch={"stage": "retrieving_knowledge"},
            ).model_dump(),
        }
        return _checkpoint(
            state,
            completed_node="knowledge_node",
            next_node="reviewer_node",
            update=update,
        )
    error_code = result.error_code or "knowledge_retrieval_failed"
    outcome_status = (
        "retryable_error" if error_code == "knowledge_retrieval_failed" else "denied"
    )
    update = {
        "knowledge_result": {
            "status": "failed",
            "error": result.error or "文档检索失败",
            "error_code": error_code,
        },
        "knowledge_outcome": NodeOutcome(
            status=outcome_status,
            output={},
            error_code=error_code,
            retry_hint="retry" if outcome_status == "retryable_error" else "stop",
            checkpoint_patch={"stage": "retrieving_knowledge"},
        ).model_dump(),
        "error": result.error,
    }
    return _checkpoint(
        state,
        completed_node="knowledge_node",
        next_node="reviewer_node",
        update=update,
    )


def data_node(state: WorkflowState) -> dict:
    """
    Data 节点：执行 SQL 查询。

    “使用 resolved_question，否则回退原始问题”。和 state["user_id"]，
    DataAgent 根据 question 生成候选 SQL，随后自行校验并执行。
    写 state["data_result"]。
    """

    _set_stage(state, "querying_data")
    data_source = state.get("business_data_source")
    snapshot_data = state.get("schema_catalog")
    if data_source is not None and snapshot_data is not None:
        catalog = SnapshotCatalog.from_snapshot(snapshot_data)
        tool_runtime = state.get("tool_runtime")
        if tool_runtime is not None:
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
        if (
            state.get("routing_action") == "retry_data"
            and state.get("cached_knowledge_result") is not None
            and state.get("cache_scope_fingerprint") == state.get("scope_fingerprint")
        ):
            update["knowledge_result"] = state["cached_knowledge_result"]
        update["data_outcome"] = NodeOutcome(
            status="succeeded",
            output=update["data_result"],
            checkpoint_patch={"stage": "querying_data"},
        ).model_dump()
        return _checkpoint(
            state,
            completed_node="data_node",
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
        return _checkpoint(
            state,
            completed_node="data_node",
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
        return _checkpoint(
            state,
            completed_node="data_node",
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
    return _checkpoint(
        state,
        completed_node="data_node",
        next_node=(
            "knowledge_node"
            if (state.get("plan") or {}).get("route") == "hybrid"
            else "reviewer_node"
        ),
        update=update,
    )


def reviewer_node(state: WorkflowState) -> dict:
    """
    Reviewer 节点：检查一致性，输出最终回答。

    读 state["data_result"] 和 state["knowledge_result"]，
    写 state["review_result"] 和 state["final_answer"]。
    """
    _set_stage(state, "composing_report")
    agent = ReviewerAgent()
    if hasattr(agent, "set_citation_validator"):
        agent.set_citation_validator(validate_citations)
    reviewer_context = {
        "plan": state.get("plan") or {},
        "data_result": state.get("data_result", {}),
        "knowledge_result": state.get("knowledge_result", {}),
    }
    if state.get("semantic_review_enabled"):
        reviewer_context["semantic_review_enabled"] = True
    with model_node_scope("reviewer"):
        result = agent.run(
            AgentInput(
                question=_effective_question(state),
                user_id=state["user_id"],
                context=reviewer_context,
            )
        )
    if result.success:
        review_result = result.evidence[0] if result.evidence else {}
        report = (
            review_result.get("report") if isinstance(review_result, dict) else None
        )
        if isinstance(review_result.get("answer_validation"), dict) and not all(
            value is not False
            for key, value in review_result["answer_validation"].items()
            if key.endswith("_valid")
        ):
            review_outcome = "validation_failed"
        elif isinstance(report, dict) and report.get("status") == "failed":
            review_outcome = "exhausted"
        elif review_result.get("review_status") in {"complete", "completed"}:
            review_outcome = "passed"
        else:
            review_outcome = "partial"
        update = {
            "review_result": {**review_result, "review_outcome": review_outcome},
            "final_answer": result.answer or "分析完成，详见证据",
            "reviewer_outcome": NodeOutcome(
                status=(
                    "succeeded"
                    if review_outcome == "passed"
                    else "insufficient_evidence"
                    if review_outcome == "partial"
                    else "repairable_error"
                ),
                output={"review_status": review_outcome},
                error_code=(
                    "report_validation_failed"
                    if review_outcome == "validation_failed"
                    else None
                ),
                retry_hint="repair"
                if review_outcome == "validation_failed"
                else "stop",
                checkpoint_patch={"stage": "composing_report"},
            ).model_dump(),
        }
        return _checkpoint(
            state,
            completed_node="reviewer_node",
            next_node="smart_router_node",
            update=update,
        )
    return _checkpoint(
        state,
        completed_node="reviewer_node",
        next_node="smart_router_node",
        update={
            "error": result.error,
            "final_answer": None,
            "reviewer_outcome": NodeOutcome(
                status="retryable_error" if result.retryable else "denied",
                output={},
                error_code=result.error_code or "reviewer_failed",
                retry_hint="retry" if result.retryable else "stop",
                checkpoint_patch={"stage": "composing_report"},
            ).model_dump(),
        },
    )


def smart_router_node(state: WorkflowState) -> dict:
    """Bounded policy engine: choose a node from typed execution state only."""
    action, reason = choose_next_action(state)
    retries = state.get("external_retry_count", 0)
    maximum = state.get("max_external_retries", MAX_EXTERNAL_RETRIES)
    if action != "stop" and retries >= maximum:
        action, reason = "stop", "external_retry_budget_exhausted"

    history = [
        *(state.get("loop_history") or []),
        {
            "attempt": retries,
            "action": action,
            "reason": reason,
            "data_status": (state.get("data_result") or {}).get("status"),
            "knowledge_status": (state.get("knowledge_result") or {}).get("status"),
        },
    ]
    if action == "stop":
        existing_terminal = state.get("terminal_result") or {}
        return {
            "routing_action": action,
            "loop_stop_reason": reason,
            "loop_history": history,
            "terminal_result": {
                **existing_terminal,
                "outcome": existing_terminal.get("outcome", "completed"),
                "reason": existing_terminal.get("reason", reason),
            },
        }

    feedback = build_feedback(state, action, reason)
    updates = {
        "routing_action": action,
        "routing_feedback": feedback,
        "external_retry_count": retries + 1,
        "loop_history": history,
    }
    if action == "retry_data":
        updates.update(
            {
                "cached_knowledge_result": state.get("knowledge_result"),
                "cache_scope_fingerprint": state.get("scope_fingerprint"),
            }
        )
    elif action == "retry_knowledge":
        updates.update(
            {
                "cached_data_result": state.get("data_result"),
                "cache_scope_fingerprint": state.get("scope_fingerprint"),
            }
        )
    elif action == "replan":
        updates.update(
            {
                "plan": None,
                "data_result": None,
                "knowledge_result": None,
                "data_outcome": None,
                "knowledge_outcome": None,
                "review_result": None,
                "cached_data_result": None,
                "cached_knowledge_result": None,
                "cache_scope_fingerprint": None,
                "empty_result_replanned": state.get("empty_result_replanned")
                or reason == "empty_result_scope_check",
            }
        )
    return updates
