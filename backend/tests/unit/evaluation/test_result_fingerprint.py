from app.modules.evaluation.result_fingerprint import (
    result_fingerprint_from_data_result,
    revenue_month_comparison_fingerprint_from_data_result,
)


def _data_result(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "ready",
        "evidence": [
            {
                "sql": "SELECT region, sales FROM monthly_sales",
                "purpose": "查询区域销售额",
                "columns": ["region", "sales"],
                "rows": [["EAST", "100"]],
            }
        ],
    }
    result.update(overrides)
    return result


def test_fingerprint_is_stable_for_a_validated_result() -> None:
    assert result_fingerprint_from_data_result(_data_result()) == {
        "algorithm": "sha256",
        "value": "9982d064b3a28d3d5da44b0e1ed99ff684a1cfd085b1970339f4b66d543de4f1",
    }


def test_fingerprint_ignores_sql_and_purpose() -> None:
    first = result_fingerprint_from_data_result(_data_result())
    second = result_fingerprint_from_data_result(
        _data_result(
            evidence=[
                {
                    "sql": "SELECT a_different_query",
                    "purpose": "不同的执行理由",
                    "columns": ["region", "sales"],
                    "rows": [["EAST", "100"]],
                }
            ]
        )
    )

    assert second == first


def test_fingerprint_uses_the_validated_single_metric_concept_not_its_display_alias() -> (
    None
):
    first = result_fingerprint_from_data_result(
        _data_result(
            evidence=[
                {
                    "columns": ["销售额"],
                    "rows": [["1847604.72"]],
                    "query_contract": {"required_concepts": ["销售额"]},
                }
            ]
        )
    )
    aliased = result_fingerprint_from_data_result(
        _data_result(
            evidence=[
                {
                    "columns": ["华东区销售额"],
                    "rows": [["1847604.72"]],
                    "query_contract": {"required_concepts": ["销售额"]},
                }
            ]
        )
    )

    assert first == {
        "algorithm": "sha256",
        "value": "7c587b5fb455ebe3e3a51ecfe11a23325708b41653cd4eb012798489a1bb46cd",
    }
    assert aliased == first


def test_fingerprint_changes_when_returned_rows_change() -> None:
    first = result_fingerprint_from_data_result(_data_result())
    changed = result_fingerprint_from_data_result(
        _data_result(
            evidence=[
                {
                    "columns": ["region", "sales"],
                    "rows": [["EAST", "99"]],
                }
            ]
        )
    )

    assert changed is not None
    assert changed != first


def test_fingerprint_is_unknown_for_unvalidated_or_malformed_results() -> None:
    assert result_fingerprint_from_data_result(_data_result(status="failed")) is None
    assert (
        result_fingerprint_from_data_result(
            _data_result(evidence=[{"columns": ["sales"], "rows": [[1, 2]]}])
        )
        is None
    )


def test_fingerprint_keeps_a_validated_no_matching_records_result() -> None:
    fingerprint = result_fingerprint_from_data_result(
        {
            "status": "insufficient_evidence",
            "error_code": "no_matching_records",
        }
    )

    assert fingerprint == {
        "algorithm": "sha256",
        "value": "4012d5a713b509655890e39fbc864ab4054cbd784178f3a0485e882309860ded",
    }
    assert (
        result_fingerprint_from_data_result(
            {"status": "insufficient_evidence", "error_code": "insufficient_schema"}
        )
        is None
    )


def test_revenue_month_comparison_fingerprint_normalizes_aliases_and_row_order() -> (
    None
):
    expected = revenue_month_comparison_fingerprint_from_data_result(
        {
            "status": "ready",
            "evidence": [
                {
                    "columns": ["月份", "销售额"],
                    "rows": [["2025-08", "201.00"], ["2025-07", "100"]],
                    "metric_assessment": {
                        "status": "supported",
                        "metric_definition_ref": "revenue/v1",
                    },
                }
            ],
        },
        period="2025-08 compared_to 2025-07",
    )
    actual = revenue_month_comparison_fingerprint_from_data_result(
        {
            "status": "ready",
            "evidence": [
                {
                    "columns": ["revenue", "month"],
                    "rows": [["100.00", "2025-07-01"], ["201", "2025-08"]],
                    "metric_assessment": {
                        "status": "supported",
                        "metric_definition_ref": "revenue/v1",
                    },
                }
            ],
        },
        period="2025-08 compared_to 2025-07",
    )

    assert expected is not None
    assert actual == expected


def test_revenue_month_comparison_fingerprint_fails_closed_for_ambiguous_rows() -> None:
    result = revenue_month_comparison_fingerprint_from_data_result(
        {
            "status": "ready",
            "evidence": [
                {
                    "columns": ["month", "revenue"],
                    "rows": [["2025-07", "100"], ["2025-07", "201"]],
                    "metric_assessment": {
                        "status": "supported",
                        "metric_definition_ref": "revenue/v1",
                    },
                }
            ],
        },
        period="2025-08 compared_to 2025-07",
    )

    assert result is None
