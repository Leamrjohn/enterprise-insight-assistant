import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/evaluation"))

from run_plan_rules_evaluation import score_rules


def test_score_rules_counts_right_wrong_and_unmatched():
    cases = [
        {
            "case_id": "doc",
            "question": "哪些资料支持SUP-003传感器批次异常？",
            "acceptable": ["analyze/knowledge_only"],
        },
        {
            "case_id": "doc-wrong",
            "question": "哪些资料支持CUST-0280回款风险上升？",
            "acceptable": ["analyze/hybrid"],
        },
        {
            "case_id": "plain",
            "question": "为什么华东区8月销售额下降了？",
            "acceptable": ["analyze/hybrid"],
        },
    ]

    report = score_rules(cases)

    assert report["unmatched"] == 1
    assert report["rules"]["R2"] == {"hits": 2, "right": 1, "wrong": ["doc-wrong"]}
