from app.modules.analysis.metrics.claim_validation import assess_numeric_assertion
from app.modules.analysis.data.query_contract import NumericAssertion


def _assertion(**overrides: object) -> NumericAssertion:
    values = {"column": "销售额", "operator": "greater_than", "value": "100"}
    values.update(overrides)
    return NumericAssertion.model_validate(values)


def test_numeric_claim_is_supported_by_one_metric_result() -> None:
    assessment = assess_numeric_assertion(
        _assertion(),
        columns=["销售额"],
        rows=[["101.20"]],
        metric_status="supported",
    )

    assert assessment.status == "supported"


def test_numeric_claim_is_refuted_by_one_metric_result() -> None:
    assessment = assess_numeric_assertion(
        _assertion(operator="equals", value="100"),
        columns=["销售额"],
        rows=[["101.20"]],
        metric_status="supported",
    )

    assert assessment.status == "refuted"


def test_numeric_claim_is_insufficient_without_a_supported_single_numeric_result() -> None:
    assessment = assess_numeric_assertion(
        _assertion(),
        columns=["销售额"],
        rows=[["101"], ["102"]],
        metric_status="supported",
    )

    assert assessment.status == "insufficient"


def test_numeric_claim_is_irrelevant_when_column_is_not_returned() -> None:
    assessment = assess_numeric_assertion(
        _assertion(column="订单数量"),
        columns=["销售额"],
        rows=[["101"]],
        metric_status="supported",
    )

    assert assessment.status == "irrelevant"
