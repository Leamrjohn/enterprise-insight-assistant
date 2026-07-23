import pytest
from pydantic import ValidationError

from app.schemas.plannerdecision import PlannerDecision


def test_analyze_decision_requires_a_resolved_question() -> None:
    with pytest.raises(ValidationError, match="resolved_question"):
        PlannerDecision(
            action="analyze",
            route="hybrid",
            reason="需要数据和资料。",
            clarification_question=None,
            response_message=None,
            resolved_question=None,
        )


def test_analyze_decision_keeps_a_standalone_resolved_question() -> None:
    decision = PlannerDecision(
        action="analyze",
        route="hybrid",
        reason="需要数据和资料。",
        clarification_question=None,
        response_message=None,
        resolved_question="分析华南区 2025 年 8 月相较 7 月销售额的变化及原因。",
    )

    assert decision.resolved_question == (
        "分析华南区 2025 年 8 月相较 7 月销售额的变化及原因。"
    )


def test_non_analysis_decision_must_not_include_a_resolved_question() -> None:
    with pytest.raises(ValidationError, match="resolved_question"):
        PlannerDecision(
            action="needs_clarification",
            route=None,
            reason="缺少时间范围。",
            clarification_question="请补充需要比较的月份。",
            response_message=None,
            resolved_question="分析华东区销售额。",
        )
