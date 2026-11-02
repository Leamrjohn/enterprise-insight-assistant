"""The scorer must separate right answers from wrong ones, whatever the aliases."""

from decimal import Decimal

import pytest
from app.modules.evaluation.sql_results import score_result, summarize


def _rows(actual, reference, **kwargs) -> str:
    return score_result(
        expect="rows",
        agent_success=True,
        actual_rows=actual,
        reference_rows=reference,
        **kwargs,
    )


def test_same_value_in_a_different_type_is_correct():
    assert _rows([["100.50"]], [(Decimal("100.5"),)]) == "correct"


def test_wrong_value_is_detected():
    assert _rows([["100.51"]], [(Decimal("100.50"),)]) == "wrong_values"


def test_extra_columns_pass_but_are_labelled():
    verdict = _rows([["华东", "100.50"]], [(Decimal("100.50"),)])
    assert verdict == "correct_extra_columns"


def test_unordered_rows_match_in_any_order():
    assert _rows([["2"], ["1"]], [(1,), (2,)]) == "correct"


def test_ordered_case_rejects_a_wrong_order():
    assert _rows([["2"], ["1"]], [(1,), (2,)], ordered=True) == "wrong_values"


def test_text_is_only_compared_when_requested():
    actual, reference = [["甲公司", "5"]], [("乙公司", 5)]
    assert _rows(actual, reference) == "correct"
    assert _rows(actual, reference, compare_text=True) == "wrong_values"


def test_pivoted_answer_is_not_a_full_pass():
    verdict = _rows([["1", "2"]], [(1,), (2,)])
    assert verdict == "same_values_other_shape"


def test_missing_rows_are_detected():
    assert _rows([["1"]], [(1,), (2,)]) == "wrong_row_count"


@pytest.mark.parametrize("empty", [[], [[None]]])
def test_empty_result_for_a_real_answer_is_false_empty(empty):
    assert _rows(empty, [(1,)]) == "false_empty"


@pytest.mark.parametrize("empty", [[], [[None]]])
def test_no_data_case_accepts_empty_results(empty):
    verdict = score_result(expect="no_data", agent_success=True, actual_rows=empty)
    assert verdict == "correct_no_data"


def test_no_data_case_accepts_the_explicit_error_code():
    verdict = score_result(
        expect="no_data",
        agent_success=False,
        actual_rows=[],
        error_code="no_matching_records",
    )
    assert verdict == "correct_no_data"


def test_zero_invented_for_missing_data_is_wrong():
    verdict = score_result(expect="no_data", agent_success=True, actual_rows=[["0"]])
    assert verdict == "value_for_no_data"


def test_rejection_case_fails_when_rows_come_back():
    assert (
        score_result(expect="rejected", agent_success=True, actual_rows=[["1"]])
        == "answered_should_reject"
    )
    assert (
        score_result(expect="rejected", agent_success=False, actual_rows=None)
        == "correct"
    )


def test_agent_failure_is_reported_with_its_code():
    verdict = score_result(
        expect="rows",
        agent_success=False,
        actual_rows=None,
        reference_rows=[(1,)],
        error_code="sql_validation_error",
    )
    assert verdict == "failed_sql_validation_error"


def test_summary_counts_passes_by_split():
    summary = summarize(
        [
            {"case_id": "a", "split": "development", "verdict": "correct"},
            {"case_id": "b", "split": "development", "verdict": "wrong_values"},
            {"case_id": "c", "split": "heldout", "verdict": "correct_no_data"},
        ]
    )
    assert summary["accuracy"] == pytest.approx(2 / 3)
    assert summary["by_split"] == {"development": 0.5, "heldout": 1.0}
    assert summary["not_passed"] == ["b"]
