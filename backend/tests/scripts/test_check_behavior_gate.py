"""E10a: an evaluation that falls below its baseline fails the gate."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/evaluation"))

from check_behavior_gate import (
    DEFAULT_BASELINE,
    EXTRACTORS,
    compare,
    main,
    plan_rules_counts,
    planner_route_counts,
    sql_results_counts,
)


def _planner(*actuals):
    return {
        "results": [
            {"actual": actual, "correct": actual == "analyze/data_only"}
            for actual in actuals
        ]
    }


def test_planner_counts_right_answers_and_errors():
    counts = planner_route_counts(_planner("analyze/data_only", "error", "x/y"))

    assert counts == {"cases": 3, "correct": 1, "errors": 1}


def test_a_drop_below_a_min_baseline_fails():
    problems = compare({"correct": 31}, {"min": {"correct": 32}})

    assert problems == ["correct: 31 < baseline 32"]


def test_a_rise_above_a_max_baseline_fails():
    problems = compare({"errors": 2}, {"max": {"errors": 1}})

    assert problems == ["errors: 2 > baseline 1"]


def test_an_equal_count_must_match_exactly():
    assert compare({"cases": 42}, {"equal": {"cases": 43}}) == [
        "cases: 42 != baseline 43"
    ]


def test_a_count_missing_from_the_report_fails():
    assert compare({}, {"min": {"correct": 1}}) == ["correct: missing from the report"]


def test_improvements_pass():
    assert (
        compare(
            {"correct": 40, "errors": 0}, {"min": {"correct": 32}, "max": {"errors": 1}}
        )
        == []
    )


def test_plan_rules_counts_each_rule_and_the_combined_route():
    report = {
        "rules": {
            "R2": {"hits": 3, "right": 2, "wrong": ["a"]},
            "R5": {"hits": 1, "right": 1, "wrong": []},
        },
        "comparison": {"with_rules": {"correct": 9}, "conflicts": []},
    }

    assert plan_rules_counts(report) == {
        "R2.right": 2,
        "R2.wrong": 1,
        "R5.right": 1,
        "R5.wrong": 0,
        "with_rules.correct": 9,
        "conflicts": 0,
    }


def test_sql_counts_a_wrong_number_let_through_separately_from_a_refusal():
    report = {
        "results": [
            {"verdict": "correct"},
            {"verdict": "correct_no_data"},
            {"verdict": "failed_metric_contract_insufficient"},
            {"verdict": "wrong_values"},
        ]
    }

    assert sql_results_counts(report) == {"cases": 4, "passed": 2, "released_wrong": 1}


def test_main_exits_1_on_regression_and_2_on_an_unreadable_report(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"components": {"planner_route": {"min": {"correct": 2}}}}),
        encoding="utf-8",
    )
    report = tmp_path / "planner.json"
    report.write_text(
        json.dumps(_planner("analyze/data_only", "error")), encoding="utf-8"
    )

    assert main(["planner_route", str(report), "--baseline", str(baseline)]) == 1
    assert "correct: 1 < baseline 2" in capsys.readouterr().out

    report.write_text("{}", encoding="utf-8")
    assert main(["planner_route", str(report), "--baseline", str(baseline)]) == 2


def test_the_checked_in_baseline_covers_every_component():
    baseline = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))

    assert set(baseline["components"]) == set(EXTRACTORS)
    for component in baseline["components"].values():
        assert component.get("min") or component.get("max")


def _policy(policy_id="paragraph_jieba_rrf_rerank_v1"):
    return {
        "policy_id": policy_id,
        "final": {"overall": {"cases": 4, "hit_at_1": 0.5, "hit_at_3": 0.75}},
        "candidates": {"overall": {"cases": 4, "hit_at_10": 1.0}},
        "answer_in_prompt": {"cases": 2, "rate": 0.5},
        "version_traps": {
            "overall": {"right_version_first": 3, "wrong_version_above_right": 0}
        },
    }


def test_retrieval_counts_turn_rates_back_into_question_counts():
    from check_behavior_gate import retrieval_counts

    assert retrieval_counts({"policies": [_policy()]}) == {
        "cases": 4,
        "final.hit_at_1": 2,
        "final.hit_at_3": 3,
        "candidates.hit_at_10": 4,
        "answer_in_prompt": 1,
        "traps.right_version_first": 3,
        "traps.wrong_version_above_right": 0,
    }


def test_retrieval_refuses_a_report_with_several_policies():
    import pytest
    from check_behavior_gate import retrieval_counts

    with pytest.raises(ValueError, match="exactly one"):
        retrieval_counts({"policies": [_policy(), _policy("other")]})
