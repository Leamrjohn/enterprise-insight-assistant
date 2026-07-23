"""LangGraph 工作流节点 —— 每个节点封装一个 Agent 调用"""

from app.agents.protocol import AgentInput
from app.agents.planner import PlannerAgent
from app.agents.knowledge import KnowledgeAgent
from app.agents.data import DataAgent
from app.agents.reviewer import ReviewerAgent
from app.services.workflow_state import WorkflowState


def _effective_question(state: WorkflowState) -> str:
    """Use the Planner's standalone question without overwriting user input."""
    return (state.get("plan") or {}).get("resolved_question") or state["question"]


def planner_node(state: WorkflowState) -> dict:
    """
    Planner 节点：分析问题，输出计划。

    读 state["question"] 和 state["user_id"]，
    写 state["plan"]。
    """
    agent = PlannerAgent()
    result = agent.run(
        AgentInput(
            question=state["question"],
            user_id=state["user_id"],
            context={
                "conversation_context": state.get("conversation_context"),
            },
        )
    )
    if result.success and result.plan:
        return {
            "plan": result.plan,
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


def planner_terminal_node(state: WorkflowState) -> dict:
    """Return a deterministic terminal response for non-analysis Planner actions."""
    plan = state.get("plan") or {}
    action = plan.get("action")

    if action == "needs_clarification":
        answer = (
            plan.get("clarification_question")
            or "请补充需要分析的指标、时间、区域或对象。"
        )
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
    agent = KnowledgeAgent()
    result = agent.run(
        AgentInput(
            question=_effective_question(state),
            user_id=state["user_id"],
        )
    )
    if result.success:
        return {
            "knowledge_result": {
                "status": ("ready" if result.evidence else "insufficient_evidence"),
                "answer": result.answer,
                "evidences": result.evidence,
            }
        }
    return {
        "knowledge_result": {
            "status": "failed",
            "error": result.error or "文档检索失败",
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

    agent = DataAgent()
    result = agent.run(
        AgentInput(
            question=_effective_question(state),
            user_id=state["user_id"],
        )
    )
    if result.success:
        return {
            "data_result": {
                "status": "ready",
                "evidence": result.evidence,
                "attempts": result.attempts,
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
    agent = ReviewerAgent()
    result = agent.run(
        AgentInput(
            question=_effective_question(state),
            user_id=state["user_id"],
            context={
                "plan": state.get("plan") or {},
                "data_result": state.get("data_result", {}),
                "knowledge_result": state.get("knowledge_result", {}),
            },
        )
    )
    if result.success:
        return {
            "review_result": result.evidence[0] if result.evidence else {},
            "final_answer": result.answer or "分析完成，详见证据",
        }
    return {"error": result.error, "final_answer": None}
