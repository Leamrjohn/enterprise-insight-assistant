"""LangGraph 工作流节点 —— 每个节点封装一个 Agent 调用"""

from app.agents.protocol import AgentInput
from app.agents.planner import PlannerAgent
from app.agents.knowledge import KnowledgeAgent
from app.agents.data import DataAgent
from app.agents.reviewer import ReviewerAgent
from app.services.workflow_state import WorkflowState


def planner_node(state: WorkflowState) -> dict:
    """
    Planner 节点：分析问题，输出计划。

    读 state["question"] 和 state["user_id"]，
    写 state["plan"]。
    """
    agent = PlannerAgent()
    result = agent.run(AgentInput(
        question=state["question"],
        user_id=state["user_id"],
    ))
    if result.success and result.evidence:
        return {"plan": result.evidence[0].get("plan")}
    return {"error": result.error, "plan": None}


def knowledge_node(state: WorkflowState) -> dict:
    """
    Knowledge 节点：检索文档证据。

    读 state["question"] 和 state["user_id"]，
    写 state["knowledge_result"]。
    """
    agent = KnowledgeAgent()
    result = agent.run(AgentInput(
        question=state["question"],
        user_id=state["user_id"],
    ))
    if result.success:
        return {"knowledge_result": {"evidences": result.evidence}}
    return {"knowledge_result": None, "error": result.error}


def data_node(state: WorkflowState) -> dict:
    """
    Data 节点：执行 SQL 查询。

    读 state["question"] 和 state["user_id"]，
    context.sql 需要由上游（Planner）预先填入 SQL。
    写 state["data_result"]。
    """
    sql = (state.get("plan") or {}).get("sql", "")
    agent = DataAgent()
    result = agent.run(AgentInput(
        question=state["question"],
        user_id=state["user_id"],
        context={"sql": sql},
    ))
    if result.success:
        return {"data_result": {"evidence": result.evidence}}
    return {"data_result": None, "error": result.error}


def reviewer_node(state: WorkflowState) -> dict:
    """
    Reviewer 节点：检查一致性，输出最终回答。

    读 state["data_result"] 和 state["knowledge_result"]，
    写 state["review_result"] 和 state["final_answer"]。
    """
    agent = ReviewerAgent()
    result = agent.run(AgentInput(
        question=state["question"],
        user_id=state["user_id"],
        context={
            "data_result": state.get("data_result", {}),
            "knowledge_result": state.get("knowledge_result", {}),
        },
    ))
    if result.success:
        return {
            "review_result": result.evidence[0] if result.evidence else {},
            "final_answer": result.answer or "分析完成，详见证据",
        }
    return {"error": result.error, "final_answer": None}
