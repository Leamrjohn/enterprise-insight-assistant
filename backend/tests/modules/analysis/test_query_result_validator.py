from app.modules.analysis.query_contract import QueryContract
from app.modules.analysis.query_validation import assess_query_result


def test_empty_rows_are_not_promoted_to_supported_evidence() -> None:
    assessment = assess_query_result(
        columns=["销售额"],
        rows=[],
        contract=QueryContract(
            required_concepts=["销售额", "2026年6月"],
            expected_columns=["销售额"],
            result_kind="aggregate",
        ),
    )

    assert assessment.status == "no_matching_records"


def test_aggregate_zero_is_a_supported_observation_not_an_empty_result() -> None:
    assessment = assess_query_result(
        columns=["销售额"],
        rows=[(0,)],
        contract=QueryContract(
            required_concepts=["销售额"],
            expected_columns=["销售额"],
            result_kind="aggregate",
        ),
    )

    assert assessment.status == "supported"


def test_result_columns_must_match_the_query_contract() -> None:
    assessment = assess_query_result(
        columns=["订单数量"],
        rows=[(3,)],
        contract=QueryContract(
            required_concepts=["销售额"],
            expected_columns=["销售额"],
            result_kind="aggregate",
        ),
    )

    assert assessment.status == "invalid_result_shape"
    assert "销售额" in assessment.reason
