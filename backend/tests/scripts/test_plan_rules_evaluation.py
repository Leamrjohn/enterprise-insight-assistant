import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/evaluation"))

import pytest
from run_plan_rules_evaluation import (
    MIN_SAMPLES,
    LabelSetError,
    compare_routes,
    content_sha256,
    load_cases,
    main,
    planner_decisions,
    planner_resolved,
    score_rules,
)


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


def _label_doc(status="frozen", cases=None):
    doc = {
        "version": "plan-rules-heldout/test",
        "status": status,
        "cases": [{"case_id": "a", "question": "q", "acceptable": ["analyze/hybrid"]}]
        if cases is None
        else cases,
    }
    if status == "frozen":
        doc["content_sha256"] = content_sha256(doc["cases"])
    return doc


def test_load_cases_refuses_a_frozen_set_without_its_hash():
    doc = _label_doc()
    del doc["content_sha256"]

    with pytest.raises(LabelSetError, match="hash"):
        load_cases(doc)


def test_load_cases_refuses_a_frozen_set_edited_after_freezing():
    doc = _label_doc()
    doc["cases"][0]["acceptable"] = ["analyze/data_only"]

    with pytest.raises(LabelSetError, match="hash"):
        load_cases(doc)


def test_content_sha256_ignores_key_order():
    assert content_sha256([{"a": 1, "b": "华"}]) == content_sha256(
        [{"b": "华", "a": 1}]
    )


def test_load_cases_refuses_an_empty_set():
    with pytest.raises(LabelSetError, match="no cases"):
        load_cases(_label_doc(cases=[]))


def test_load_cases_refuses_a_draft_set_unless_allowed():
    with pytest.raises(LabelSetError, match="draft"):
        load_cases(_label_doc(status="draft"))
    assert len(load_cases(_label_doc(status="draft"), allow_unfrozen=True)) == 1


def test_load_cases_refuses_when_every_case_is_excluded():
    cases = [{"case_id": "a", "question": "q", "acceptable": [], "included": False}]
    with pytest.raises(LabelSetError, match="no cases"):
        load_cases(_label_doc(cases=cases))


@pytest.mark.parametrize("status, cases", [("draft", None), ("frozen", [])])
def test_main_exits_non_zero_on_a_draft_or_empty_set(tmp_path, status, cases):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(_label_doc(status, cases)), encoding="utf-8")

    with pytest.raises(SystemExit) as stopped:
        main(["--labels", str(labels)])

    assert stopped.value.code != 0


def test_score_rules_lists_rules_short_of_samples():
    cases = [
        {
            "case_id": f"doc-{i}",
            "question": "哪些资料支持SUP-003传感器批次异常？",
            "acceptable": ["analyze/knowledge_only"],
        }
        for i in range(MIN_SAMPLES)
    ]

    report = score_rules(cases)

    assert report["min_samples"] == MIN_SAMPLES
    assert "R2" not in report["short_of_samples"]
    assert {"R3", "R4", "R5"} <= set(report["short_of_samples"])


DOC = "哪些资料支持SUP-003传感器批次异常？"  # R2 only
NUMBER = "华东区销售额是多少？"  # R4 only
COMPARE_DOCS = "比较两份制度文档的区别"  # R2 and R5 disagree


def test_compare_routes_counts_right_and_wrong_clarifications_per_mode():
    cases = [
        # Planner wrong, rule right: enabling helps.
        {"case_id": "doc", "question": DOC, "acceptable": ["analyze/knowledge_only"]},
        # Planner right, rule asks back wrongly: enabling adds a wrong clarification.
        {"case_id": "num", "question": NUMBER, "acceptable": ["analyze/data_only"]},
        # No rule: the Planner's decision stands in both modes.
        {
            "case_id": "plain",
            "question": "为什么华东区8月销售额下降了？",
            "acceptable": ["analyze/hybrid"],
        },
    ]
    planner = {
        "doc": "analyze/hybrid",
        "num": "analyze/data_only",
        "plain": "analyze/hybrid",
    }

    report = compare_routes(cases, planner)

    assert report["planner_only"] == {"correct": 2, "wrong_clarifications": 0}
    assert report["with_rules"] == {"correct": 2, "wrong_clarifications": 1}
    assert report["changed"] == [
        {
            "case_id": "doc",
            "planner": "analyze/hybrid",
            "with_rules": "analyze/knowledge_only",
            "effect": "fixed",
        },
        {
            "case_id": "num",
            "planner": "analyze/data_only",
            "with_rules": "needs_clarification/None",
            "effect": "broke",
        },
    ]


def test_compare_routes_only_applies_enabled_rules():
    cases = [
        {"case_id": "num", "question": NUMBER, "acceptable": ["analyze/data_only"]}
    ]

    report = compare_routes(cases, {"num": "analyze/data_only"}, enabled={"R2"})

    assert report["with_rules"] == {"correct": 1, "wrong_clarifications": 0}
    assert report["changed"] == []


def test_compare_routes_reports_a_rule_conflict():
    cases = [
        {
            "case_id": "cmp",
            "question": COMPARE_DOCS,
            "acceptable": ["analyze/knowledge_only"],
        }
    ]

    report = compare_routes(cases, {"cmp": "analyze/knowledge_only"})

    assert report["conflicts"] == [{"case_id": "cmp", "rules": ["R2", "R5"]}]
    assert report["with_rules"]["correct"] == 1


def test_compare_routes_fails_when_a_planner_result_is_missing():
    cases = [
        {"case_id": "doc", "question": DOC, "acceptable": ["analyze/knowledge_only"]}
    ]

    with pytest.raises(LabelSetError, match="doc"):
        compare_routes(cases, {})


def test_planner_decisions_reads_the_route_evaluation_report():
    report = {"results": [{"case_id": "a", "actual": "analyze/hybrid"}]}

    assert planner_decisions(report) == {"a": "analyze/hybrid"}


def test_compare_routes_settles_a_conflict_by_the_arbitration_table():
    # Table row 1: R2 (routing) beats R5 (clarification), fixing a wrong Planner.
    cases = [
        {
            "case_id": "cmp",
            "question": COMPARE_DOCS,
            "acceptable": ["analyze/knowledge_only"],
        }
    ]

    report = compare_routes(cases, {"cmp": "needs_clarification/None"})

    assert report["planner_only"] == {"correct": 0, "wrong_clarifications": 1}
    assert report["with_rules"] == {"correct": 1, "wrong_clarifications": 0}
    assert report["changed"][0]["effect"] == "fixed"


def test_compare_routes_reads_the_resolved_question_of_a_follow_up():
    # Table row 2: "那华北呢？" alone hits nothing; its resolved question hits R4.
    cases = [
        {
            "case_id": "follow-up",
            "question": "那华北呢？",
            "resolved_question": "华北区销售额是多少？",
            "acceptable": ["needs_clarification/None"],
        }
    ]

    report = compare_routes(cases, {"follow-up": "analyze/data_only"})

    assert report["with_rules"]["correct"] == 1


def test_planner_resolved_reads_the_route_evaluation_report():
    report = {
        "results": [
            {"case_id": "a", "actual": "analyze/hybrid", "resolved_question": "qa"},
            # Reports recorded before B2j have no resolved_question.
            {"case_id": "b", "actual": "analyze/hybrid"},
        ]
    }

    assert planner_resolved(report) == {"a": "qa", "b": None}


def test_compare_routes_reads_the_planners_resolved_question():
    cases = [
        {
            "case_id": "follow-up",
            "question": "那华北呢？",
            "acceptable": ["needs_clarification/None"],
        }
    ]
    planner = {"follow-up": "analyze/data_only"}

    with_rewrite = compare_routes(
        cases, planner, resolved={"follow-up": "华北区销售额是多少？"}
    )
    without = compare_routes(cases, planner, resolved={"follow-up": None})

    assert with_rewrite["with_rules"]["correct"] == 1  # R4 fires on the rewrite
    assert without["with_rules"]["correct"] == 0  # the original hits nothing
