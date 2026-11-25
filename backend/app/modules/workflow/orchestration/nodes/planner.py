"""Planner 节点组：规划、语义复核、终止和规划失败。"""

import re

from app.core.config.snapshot import runtime_settings
from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.planner.planner_agent import PlannerAgent
from app.modules.analysis.planner.planner_decision import (
    enforce_explicit_document_evidence_contract,
)
from app.modules.conversations.state import STATE_SNAPSHOT_KEY
from app.modules.conversations.summary import SUMMARY_SNAPSHOT_KEY
from app.modules.reporting.semantic_review_service import SemanticReviewService
from app.modules.runtime.context.engine import ContextBudgetExceeded
from app.modules.runtime.model_governance import model_node_scope
from app.modules.workflow.orchestration.node_outcome import NodeOutcome
from app.modules.workflow.orchestration.nodes._common import (
    _checkpoint,
    _next_after_plan,
    _set_stage,
)
from app.modules.workflow.orchestration.router import (
    build_scope_fingerprint,
)
from app.modules.workflow.orchestration.state import WorkflowState

_CLARIFICATION_SLOT_LABELS = {
    "metric": "需要查询的经营指标",
    "time_range": "时间范围",
    "comparison_period": "对比时间范围",
    "region": "区域",
    "customer": "客户",
    "product": "产品",
    "object": "分析对象",
}
# Table and column names such as invoices.status or due_date never reach users.
_INTERNAL_NAME = re.compile(r"[A-Za-z]+_[A-Za-z_]+|[A-Za-z_]+\.[A-Za-z_]+")


def _render_clarification(plan: dict) -> str:
    """Show the specific question when there is one; missing slots are the fallback."""
    question = plan.get("clarification_question")
    if question and not _INTERNAL_NAME.search(question):
        return question
    clarification = plan.get("clarification")
    if not isinstance(clarification, dict):
        return "请补充需要分析的指标、时间、区域或对象。"
    slots = clarification.get("missing_slots")
    if not isinstance(slots, list) or not slots:
        return "请补充需要分析的指标、时间、区域或对象。"
    labels = [_CLARIFICATION_SLOT_LABELS.get(slot, str(slot)) for slot in slots[:3]]
    examples = clarification.get("examples")
    example_text = ""
    if isinstance(examples, list) and examples:
        example_text = "，例如：" + "；".join(str(item) for item in examples[:3])
    return "请补充" + "、".join(labels) + example_text + "。"


_FROZEN_KEYS = frozenset({STATE_SNAPSHOT_KEY, SUMMARY_SNAPSHOT_KEY})


def _planner_conversation_context(state: WorkflowState) -> dict | None:
    """The history the Planner reads; the frozen state and summary are never part of it.

    enforce swaps the regex constraints for the extracted state, as the
    long-conversation evaluation does; shadow and off leave them as they were.
    """
    context = state.get("conversation_context")
    if not context or not _FROZEN_KEYS.intersection(context):
        return context
    context = {k: v for k, v in context.items() if k not in _FROZEN_KEYS}
    extracted = state.get("conversation_state")
    if (
        runtime_settings().conversation_state_mode == "enforce"
        and extracted is not None
    ):
        context.pop("standing_constraints", None)
        context["conversation_state"] = extracted
    return context


def _planner_history_summary(state: WorkflowState) -> list[str] | None:
    """C9c: the summary frozen at task creation, sent only in enforce."""
    if runtime_settings().conversation_summary_mode != "enforce":
        return None
    frozen = (state.get("conversation_context") or {}).get(SUMMARY_SNAPSHOT_KEY)
    return (frozen or {}).get("items") or None


def planner_node(state: WorkflowState) -> dict:
    """
    Planner 节点：分析问题，输出计划。

    读 state["question"] 和 state["user_id"]，
    写 state["plan"]。
    """
    _set_stage(state, "planning", "planner_node")
    agent = PlannerAgent()
    history_summary = _planner_history_summary(state)
    with model_node_scope("planner"):
        result = agent.run(
            AgentInput(
                question=state["question"],
                user_id=state["user_id"],
                context={
                    "conversation_context": _planner_conversation_context(state),
                    **({"history_summary": history_summary} if history_summary else {}),
                    **(
                        {"planner_memory": state["planner_memory"]}
                        if state.get("planner_memory")
                        else {}
                    ),
                    **(
                        {"attachment_context": state["attachment_context"]}
                        if state.get("attachment_context")
                        else {}
                    ),
                    **(
                        {"feedback": state["routing_feedback"]}
                        if state.get("routing_feedback") is not None
                        else {}
                    ),
                    **(
                        {"retry_context": state["retry_context"]}
                        if state.get("retry_context") is not None
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
    _set_stage(state, "planning", "planner_semantic_review_node")
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
            reviewed_plan = enforce_explicit_document_evidence_contract(
                state["question"], reviewed_plan
            )
    except (
        PermanentModelError,
        RetryableModelError,
        StructuredOutputError,
        # C5: refused before any model call, so not worth retrying either.
        ContextBudgetExceeded,
    ) as error:
        retryable = isinstance(error, RetryableModelError)
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
                status="retryable_error" if retryable else "repairable_error",
                output={},
                error_code="semantic_review_failed",
                retry_hint="retry" if retryable else "repair",
                checkpoint_patch={"stage": "planning"},
            ).model_dump(),
        }
        if retryable:
            # This is a technical failure, not a user clarification.  Route it
            # through planning_failure_node so the Worker records a retryable
            # terminal result and the next attempt can resume this exact node.
            # Clearing the old analyze plan is also essential: the graph's
            # conditional edge otherwise would keep following that stale plan
            # into Data instead of taking the planning-failure branch.
            update["plan"] = None
            update["planner_failure"] = {
                "code": "semantic_review_failed",
                "message": f"Planner 语义复核失败: {error}",
                "retryable": True,
            }
        return _checkpoint(
            state,
            completed_node="planner_semantic_review_node",
            next_node="planning_failure_node" if retryable else "planner_terminal_node",
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
    terminal_result = {
        "outcome": action,
        "reason": plan.get("reason"),
    }

    if action == "needs_clarification":
        answer = _render_clarification(plan)
        clarification = plan.get("clarification") or {}
        missing_slots = clarification.get("missing_slots")
        if isinstance(missing_slots, list):
            terminal_result["missing_fields"] = [
                slot
                for slot in missing_slots
                if isinstance(slot, str) and slot in _CLARIFICATION_SLOT_LABELS
            ]
    else:
        answer = plan.get("response_message") or "当前问题无法进入分析流程。"

    return {
        "terminal_result": terminal_result,
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
