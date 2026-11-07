from datetime import date

import pytest
from app.modules.analysis.planner.facts import extract_question_facts
from app.modules.analysis.planner.rules import matching_rules, shadow_details

TODAY = date(2026, 11, 7)


@pytest.mark.parametrize(
    "question,rules",
    [
        ("哪些资料支持SUP-003传感器批次异常？", ["R2"]),
        # The number lives in the briefing, not the business database (task 864).
        ("根据库存物流简报，2025年6月电气自动化类的周转天数是多少？", ["R2"]),
        (
            "请给出华东区2025年8月的订单销售额，并根据资料说明暂停采购的原因",
            ["R3"],
        ),
        (
            "产品A在2024年3月相较2月销售额下降的原因，经营数据或资料能说明吗？",
            ["R3"],
        ),
        ("传动控制毛利压力有哪些被资料支持的因素？", ["R2"]),
        ("华东区销售额是多少？", ["R4"]),
        # A number from a document needs no time range, so R4 stays out.
        ("根据应收风险提示，对客户067建议按什么比例计提坏账准备？", ["R2"]),
        ("去年华东区销售额是多少？", []),
        ("华东区2025年8月销售额是多少？", []),
        ("本月销售额环比增长多少？", []),
        ("对比华东和华北的销售额", ["R5"]),
        ("对比华东和华北2025年8月的销售额", []),
        ("为什么华东区8月销售额下降了？", []),
    ],
)
def test_matching_rules(question, rules):
    facts = extract_question_facts(question, TODAY)

    assert [rule.rule_id for rule in matching_rules(facts)] == rules


def test_shadow_details_compare_each_hit_with_the_planner():
    facts = extract_question_facts("哪些资料支持SUP-003传感器批次异常？", TODAY)

    details = shadow_details(facts, {"action": "analyze", "route": "hybrid"})

    assert details["planner"] == "analyze/hybrid"
    assert details["hits"] == [
        {"rule": "R2", "suggests": "analyze/knowledge_only", "agrees": False}
    ]
    assert "SUP-003" not in str(details)


def test_shadow_details_without_a_plan():
    facts = extract_question_facts("华东区2025年8月销售额是多少？", TODAY)

    assert shadow_details(facts, None)["planner"] is None
