import pytest
from app.modules.analysis.planner.planner_decision import PlannerDecision
from pydantic import ValidationError


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


def test_document_question_does_not_overwrite_a_route_at_schema_boundary() -> None:
    decision = PlannerDecision.model_validate(
        {
            "action": "analyze",
            "route": "hybrid",
            "reason": "需要检索已授权合同资料。",
            "clarification_question": None,
            "response_message": None,
            "resolved_question": "有哪些资料支持 CUST-0001 暂停采购？",
            "intent": {
                "kind": "document_question",
                "required_capabilities": ["合同资料"],
                "specified_slots": ["customer"],
            },
        }
    )

    assert decision.route == "hybrid"
