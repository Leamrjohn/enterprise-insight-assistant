"""Reviewer 节点：复核报告并标记可疑记忆。"""

import logging

from app.db.session import SessionLocal, set_tenant_scope
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.reporting.citation_validation import validate_citations
from app.modules.reporting.reviewer_agent import ReviewerAgent
from app.modules.runtime.model_governance import model_node_scope
from app.modules.workflow.orchestration.node_outcome import NodeOutcome
from app.modules.workflow.orchestration.node_runner import NodeStep, run_node
from app.modules.workflow.orchestration.nodes._common import (
    _effective_question,
)
from app.modules.workflow.orchestration.state import WorkflowState

logger = logging.getLogger(__name__)


def _flag_contradicted_memories(state: WorkflowState, review_result: dict) -> None:
    """Pause memories the model doubts; a failure here must not cost the report."""
    review = review_result.get("semantic_review") if review_result else None
    flags = (review or {}).get("contradicted_memories")
    company_id = state.get("company_id")
    if not flags or company_id is None:
        return
    from app.modules.memory.service import flag_memories_from_model

    allowed_ids = {m["memory_id"] for m in state.get("planner_memory") or []}
    db = SessionLocal()
    try:
        set_tenant_scope(db, company_id)
        flag_memories_from_model(
            db, company_id=company_id, flags=flags, allowed_ids=allowed_ids
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not flag contradicted memories")
    finally:
        db.close()


def _reviewer_node(state: WorkflowState) -> NodeStep:
    """
    Reviewer 节点：检查一致性，输出最终回答。

    读 state["data_result"] 和 state["knowledge_result"]，
    写 state["review_result"] 和 state["final_answer"]。
    """
    agent = ReviewerAgent()
    if hasattr(agent, "set_citation_validator"):
        agent.set_citation_validator(validate_citations)
    reviewer_context = {
        "plan": state.get("plan") or {},
        "data_result": state.get("data_result", {}),
        "knowledge_result": state.get("knowledge_result", {}),
    }
    if state.get("retry_context") is not None:
        reviewer_context["retry_context"] = state["retry_context"]
    if state.get("semantic_review_enabled"):
        reviewer_context["semantic_review_enabled"] = True
    if state.get("planner_memory"):
        reviewer_context["planner_memory"] = state["planner_memory"]
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
        _flag_contradicted_memories(state, review_result)
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
        return NodeStep(
            next_node="smart_router_node",
            update=update,
        )
    return NodeStep(
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


reviewer_node = run_node("reviewer_node", "composing_report", _reviewer_node)
