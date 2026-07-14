"""测试 LangGraph 工作流"""
from app.services.workflow_graph import run_analysis


def test_workflow_runs_without_error():
    """工作流应该能完整运行不抛异常"""
    result = run_analysis("销售额为什么下降", user_id=1)
    assert result is not None
    assert "plan" in result
    assert result.get("plan") is not None


def test_workflow_returns_final_answer():
    """工作流应该产生最终回答"""
    result = run_analysis("客诉率为什么上升", user_id=1)
    assert "final_answer" in result
