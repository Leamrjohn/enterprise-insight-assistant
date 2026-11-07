from datetime import date

import pytest
from app.modules.analysis.planner.facts import extract_question_facts

TODAY = date(2026, 11, 7)
AUG_2025 = (date(2025, 8, 1), date(2025, 8, 31))

# question, periods, relative, quantity, document, comparison, causal
CASES = [
    # The ten smoke questions.
    (
        "区域名称为“华东”的2025年8月、状态为 delivered 的订单销售额是多少？",
        [AUG_2025],
        False,
        True,
        False,
        False,
        False,
    ),
    (
        "比较华东区2025年7月与8月已交付订单销售额。",
        [(date(2025, 7, 1), date(2025, 7, 31)), AUG_2025],
        False,
        False,
        False,
        True,
        False,
    ),
    (
        "华东区2020年3月销售额是多少？",
        [(date(2020, 3, 1), date(2020, 3, 31))],
        False,
        True,
        False,
        False,
        False,
    ),
    ("哪些资料支持SUP-003传感器批次异常？", [], False, False, True, False, False),
    ("传动控制毛利压力有哪些被资料支持的因素？", [], False, False, True, False, False),
    ("哪些资料支持CUST-0280回款风险上升？", [], False, False, True, False, False),
    (
        (
            "请给出华东区2025年8月状态为 delivered 的订单销售额；"
            "并根据资料说明 CUST-0001 合同到期与暂停采购的关系，"
            "且明确这些资料是否足以证明其是华东全部销售表现的唯一原因。"
        ),
        [AUG_2025],
        False,
        False,
        True,
        False,
        True,
    ),
    ("华东区销售额是多少？", [], False, True, False, False, False),
    (
        "根据应收风险提示，对华北汽车零部件客户067建议按什么比例计提坏账准备？",
        [],
        False,
        True,
        True,
        False,
        False,
    ),
    (
        "根据库存物流简报，2025年6月电气自动化类的周转天数是多少？",
        [(date(2025, 6, 1), date(2025, 6, 30))],
        False,
        True,
        True,
        False,
        False,
    ),
    # Other ways people ask.
    ("为什么华东区8月销售额下降了？", [], False, False, False, False, True),
    ("本月销售额环比增长多少？", [], True, True, False, True, False),
    (
        "去年华东区销售额是多少？",
        [(date(2025, 1, 1), date(2025, 12, 31))],
        True,
        True,
        False,
        False,
        False,
    ),
    ("最近三个月和上季度相比，回款情况怎么样？", [], True, False, False, True, False),
]


@pytest.mark.parametrize(
    "question,periods,relative,quantity,document,comparison,causal", CASES
)
def test_question_facts(
    question, periods, relative, quantity, document, comparison, causal
):
    facts = extract_question_facts(question, TODAY)

    assert list(facts.periods) == periods
    assert (
        facts.period_is_relative,
        facts.asks_quantity,
        facts.wants_document,
        facts.is_comparison,
        facts.is_causal,
    ) == (relative, quantity, document, comparison, causal)


def test_event_details_carry_no_question_text():
    question = "华东区2025年8月销售额是多少？"
    details = extract_question_facts(question, TODAY).event_details()

    assert details["periods"] == [["2025-08-01", "2025-08-31"]]
    assert "华东" not in str(details)
