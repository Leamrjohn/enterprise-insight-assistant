"""LangGraph 工作流节点 —— 每个节点封装一个 Agent 调用"""

from app.agents.protocol import AgentInput
from app.agents.planner import PlannerAgent
from app.agents.knowledge import KnowledgeAgent
from app.agents.data import DataAgent
from app.agents.reviewer import ReviewerAgent
from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.services.semantic_review import SemanticReviewService
from app.services.citation_validator import validate_citations
from app.services.workflow_state import WorkflowState
from app.services.workflow_router import (
    MAX_EXTERNAL_RETRIES,
    build_feedback,
    build_scope_fingerprint,
    choose_next_action,
)
from app.tools.snapshot_catalog import SnapshotCatalog


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
    result = agent.run(
        AgentInput(
            question=state["question"],
            user_id=state["user_id"],
            context={
                "conversation_context": state.get("conversation_context"),
                **(
                    {"feedback": state["routing_feedback"]}
                    if state.get("routing_feedback") is not None
                    else {}
                ),
            },
        )
    )
    if result.success and result.plan:
        return {
            "plan": result.plan,
            "scope_fingerprint": build_scope_fingerprint(state, result.plan),
            "planner_result": {
                "status": "ready",
                "attempts": result.attempts,
            },
        }
    return {
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
    }


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
        reviewed_plan = service.review_plan(
            question=state["question"],
            proposed_plan=plan,
            catalog=catalog,
        )
    except (PermanentModelError, RetryableModelError, StructuredOutputError) as error:
        return {
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
        }
    if reviewed_plan.action == "analyze" and reviewed_plan.intent is None:
        return {
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
        }
    return {
        "plan": reviewed_plan.model_dump(),
        "scope_fingerprint": build_scope_fingerprint(state, reviewed_plan.model_dump()),
        "planner_result": {
            "status": "ready",
            "attempts": {
                **((state.get("planner_result") or {}).get("attempts") or {}),
                "semantic_review_attempts": service.model_attempts,
            },
        },
    }


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
    agent = KnowledgeAgent()
    result = agent.run(
        AgentInput(
            question=_effective_question(state),
            user_id=state["user_id"],
            context={
                "company_id": state.get("company_id"),
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
        return {"knowledge_result": knowledge_result}
    return {
        "knowledge_result": {
            "status": "failed",
            "error": result.error or "文档检索失败",
            "error_code": result.error_code or "knowledge_retrieval_failed",
        },
        "error": result.error,
    }


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
        agent = DataAgent(
            data_source=data_source,
            snapshot_catalog=SnapshotCatalog.from_snapshot(snapshot_data),
        )
    else:
        agent = DataAgent()
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
    result = agent.run(
        AgentInput(
            question=_effective_question(state),
            user_id=state["user_id"],
            context=data_context,
        )
    )
    if result.success:
        update = {
            "data_result": {
                "status": "ready",
                "evidence": result.evidence,
                "attempts": result.attempts,
            }
        }
        if (
            state.get("routing_action") == "retry_data"
            and state.get("cached_knowledge_result") is not None
            and state.get("cache_scope_fingerprint") == state.get("scope_fingerprint")
        ):
            update["knowledge_result"] = state["cached_knowledge_result"]
        return update
    if result.error_code in {
        "insufficient_schema",
        "sql_semantic_unsupported",
        "no_matching_records",
        "invalid_result_shape",
        "query_contract_missing",
        "query_contract_incomplete",
    }:
        return {
            "data_result": {
                "status": "insufficient_evidence",
                "error": result.error or "当前契约快照不足以回答该问题。",
                "error_code": result.error_code,
                "attempts": result.attempts,
                "candidate": result.evidence[0] if result.evidence else None,
            }
        }
    return {
        "data_result": {
            "status": "failed",
            "error": result.error or "经营数据查询失败",
            "error_code": result.error_code,
            "attempts": result.attempts,
            "candidate": result.evidence[0] if result.evidence else None,
        },
        "error": result.error,
    }


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
        return {
            "review_result": {**review_result, "review_outcome": review_outcome},
            "final_answer": result.answer or "分析完成，详见证据",
        }
    return {"error": result.error, "final_answer": None}


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
                "review_result": None,
                "cached_data_result": None,
                "cached_knowledge_result": None,
                "cache_scope_fingerprint": None,
                "empty_result_replanned": state.get("empty_result_replanned")
                or reason == "empty_result_scope_check",
            }
        )
    return updates
