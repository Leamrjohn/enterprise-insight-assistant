from app.modules.analysis.data.query_contract import QueryContract
from app.modules.analysis.metrics.metric_validation import assess_metric_query


def _revenue_contract(**overrides: object) -> QueryContract:
    values = {
        "required_concepts": ["销售额"],
        "expected_columns": ["销售额"],
        "result_kind": "aggregate",
        "metric_definition_ref": "revenue/v1",
        "time_scope_column": "sales_orders.order_date",
    }
    values.update(overrides)
    return QueryContract.model_validate(values)


def test_revenue_metric_requires_aggregate_filter_time_and_lineage() -> None:
    assessment = assess_metric_query(
        """
        SELECT SUM(o.total_amount) AS "销售额"
        FROM sales_orders AS o
        WHERE o.status = 'delivered'
          AND o.order_date >= DATE '2025-08-01'
          AND o.order_date < DATE '2025-09-01'
        """,
        _revenue_contract(),
    )

    assert assessment.status == "supported"
    assert assessment.definition is not None
    assert assessment.definition.unit == "CNY"
    assert assessment.definition.time_semantics == "business_calendar_date"
    assert set(assessment.lineage_columns) >= {
        "sales_orders.total_amount",
        "sales_orders.order_date",
        "sales_orders.status",
    }


def test_revenue_metric_rejects_missing_mandatory_delivered_filter() -> None:
    assessment = assess_metric_query(
        """
        SELECT SUM(o.total_amount) AS "销售额"
        FROM sales_orders AS o
        WHERE o.order_date >= DATE '2025-08-01'
          AND o.order_date < DATE '2025-09-01'
        """,
        _revenue_contract(),
    )

    assert assessment.status == "insufficient"
    assert "sales_orders.status = delivered" in assessment.reason


def test_metric_contract_rejects_unknown_metric_as_irrelevant() -> None:
    assessment = assess_metric_query(
        'SELECT COUNT(*) AS "广告点击率" FROM sales_orders',
        _revenue_contract(metric_definition_ref="advertising_ctr/v1"),
    )

    assert assessment.status == "irrelevant"


def test_metric_contract_rejects_multiple_sql_statements() -> None:
    assessment = assess_metric_query(
        'SELECT SUM(total_amount) AS "销售额" FROM sales_orders; SELECT 1',
        _revenue_contract(),
    )

    assert assessment.status == "irrelevant"
    assert "单条 SELECT" in assessment.reason


def test_metric_contract_requires_frozen_comparison_months_in_time_predicate() -> None:
    assessment = assess_metric_query(
        """
        SELECT SUM(o.total_amount) AS "销售额"
        FROM sales_orders AS o
        WHERE o.status = 'delivered'
          AND o.order_date >= DATE '2025-08-01'
          AND o.order_date < DATE '2025-09-01'
        """,
        _revenue_contract(),
        evaluation_scope={"period": "2025-08 compared_to 2025-07"},
    )

    assert assessment.status == "incomplete"
    assert "2025-07" in assessment.reason


def test_metric_contract_accepts_a_range_covering_frozen_comparison_months() -> None:
    assessment = assess_metric_query(
        """
        SELECT SUM(o.total_amount) AS "销售额"
        FROM sales_orders AS o
        WHERE o.status = 'delivered'
          AND o.order_date >= DATE '2025-07-01'
          AND o.order_date < DATE '2025-09-01'
        """,
        _revenue_contract(),
        evaluation_scope={"period": "2025-08 compared_to 2025-07"},
    )

    assert assessment.status == "supported"
