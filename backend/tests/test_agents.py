"""测试四个核心 Agent"""
from app.agents.protocol import AgentInput
from app.agents.knowledge import KnowledgeAgent
from app.agents.data import DataAgent
from app.agents.planner import PlannerAgent
from app.agents.reviewer import ReviewerAgent


def test_knowledge_agent_interface():
    agent = KnowledgeAgent()
    assert agent.name == "knowledge"
    assert len(agent.description) > 0
    assert len(agent.allowed_tools) == 1


def test_knowledge_agent_exists():
    agent = KnowledgeAgent()
    assert agent is not None
    assert isinstance(agent.name, str)
    assert isinstance(agent.description, str)


def test_data_agent_interface():
    agent = DataAgent()
    assert agent.name == "data"
    assert len(agent.description) > 0
    assert len(agent.allowed_tools) == 1


def test_data_agent_missing_sql():
    agent = DataAgent()
    result = agent.run(AgentInput(question="测试", user_id=1))
    assert result.success is False
    assert result.error is not None
    assert "Planner" in (result.error or "")


def test_planner_agent_plan():
    agent = PlannerAgent()
    result = agent.run(AgentInput(question="销售额为什么下降", user_id=1))
    assert result.success is True
    plan = result.evidence[0]["plan"]
    assert plan["need_data"] is True
    assert any("DataAgent" in s for s in plan["steps"])


def test_planner_agent_no_match():
    agent = PlannerAgent()
    result = agent.run(AgentInput(question="今天天气怎么样", user_id=1))
    assert result.success is False


def test_reviewer_agent_interface():
    agent = ReviewerAgent()
    assert agent.name == "reviewer"
    assert len(agent.description) > 0
    assert len(agent.allowed_tools) == 0


def test_reviewer_agent_check():
    agent = ReviewerAgent()
    result = agent.run(AgentInput(
        question="测试",
        user_id=1,
        context={
            "data_result": {"rows": []},
            "knowledge_result": {"evidences": []},
        },
    ))
    assert result.success is True
    assert result.evidence[0]["has_conflicts"] is True
