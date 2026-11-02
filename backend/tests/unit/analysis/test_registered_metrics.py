"""Newly registered metrics: right SQL passes, near-miss SQL still fails closed."""

import pytest
from app.modules.analysis.data.query_contract import QueryContract
from app.modules.analysis.metrics.metric_validation import assess_metric_query

GROSS_PROFIT_FILTERS = """
    FROM sales_order_items i JOIN sales_orders o ON o.id = i.order_id
    WHERE o.status = 'delivered' AND o.order_date >= DATE '2025-08-01'
"""


def _contract(reference: str, time_column: str) -> QueryContract:
    return QueryContract.model_validate(
        {
            "required_concepts": ["指标"],
            "expected_columns": ["指标"],
            "result_kind": "aggregate",
            "metric_definition_ref": reference,
            "time_scope_column": time_column,
        }
    )


def _gross_profit(select: str) -> str:
    return assess_metric_query(
        f"SELECT {select} {GROSS_PROFIT_FILTERS}",
        _contract("gross_profit/v1", "sales_orders.order_date"),
    ).status


@pytest.mark.parametrize(
    "expression",
    [
        "i.line_amount - i.unit_cost * i.quantity",
        "i.line_amount - i.quantity * i.unit_cost",
        "i.line_amount - (i.unit_cost * i.quantity)",
        "(i.line_amount - i.unit_cost * i.quantity)",
    ],
)
def test_gross_profit_accepts_the_defined_formula(expression):
    assert _gross_profit(f"SUM({expression})") == "supported"


@pytest.mark.parametrize(
    "expression",
    [
        "i.line_amount + i.unit_cost * i.quantity",
        "(i.line_amount - i.unit_cost) * i.quantity",
        "i.line_amount - i.unit_cost",
        "i.line_amount",
    ],
)
def test_gross_profit_rejects_a_different_formula(expression):
    select = f"SUM({expression}), SUM(i.unit_cost), SUM(i.quantity)"
    assert _gross_profit(select) == "insufficient"


def test_gross_profit_requires_the_delivered_filter():
    status = assess_metric_query(
        "SELECT SUM(i.line_amount - i.unit_cost * i.quantity)"
        " FROM sales_order_items i JOIN sales_orders o ON o.id = i.order_id"
        " WHERE o.order_date >= DATE '2025-08-01' AND o.status IS NOT NULL",
        _contract("gross_profit/v1", "sales_orders.order_date"),
    ).status
    assert status == "insufficient"


def test_delivered_order_count_counts_the_order_id_with_the_filter():
    contract = _contract("delivered_order_count/v1", "sales_orders.order_date")
    good = (
        "SELECT COUNT(o.id) FROM sales_orders o WHERE o.status = 'delivered'"
        " AND o.order_date >= DATE '2025-01-01'"
    )
    assert assess_metric_query(good, contract).status == "supported"
    missing_filter = "SELECT COUNT(o.id) FROM sales_orders o WHERE o.order_date > NULL"
    assert assess_metric_query(missing_filter, contract).status == "insufficient"


def test_count_star_does_not_satisfy_a_count_metric():
    """A join can multiply rows, so the counted column must be visible."""
    status = assess_metric_query(
        "SELECT COUNT(*), COUNT(o.customer_id) FROM sales_orders o"
        " WHERE o.status = 'delivered' AND o.id > 0 AND o.order_date > DATE '2025-01-01'",
        _contract("delivered_order_count/v1", "sales_orders.order_date"),
    ).status
    assert status == "insufficient"


def test_expense_amount_accepts_unqualified_columns_on_a_single_table():
    status = assess_metric_query(
        "SELECT category, SUM(amount) FROM expense_entries"
        " WHERE expense_date >= DATE '2025-04-01' GROUP BY category",
        _contract("expense_amount/v1", "expense_entries.expense_date"),
    ).status
    assert status == "supported"


def test_unqualified_columns_stay_unresolved_when_two_tables_are_joined():
    status = assess_metric_query(
        "SELECT SUM(amount) FROM expense_entries e JOIN cost_centers c"
        " ON c.id = e.cost_center_id WHERE expense_date >= DATE '2025-04-01'",
        _contract("expense_amount/v1", "expense_entries.expense_date"),
    ).status
    assert status == "insufficient"


def test_revenue_target_sums_the_budget_column():
    contract = _contract("revenue_target/v1", "monthly_budgets.month")
    good = (
        "SELECT SUM(b.revenue_target) FROM monthly_budgets b"
        " WHERE b.month = DATE '2025-08-01'"
    )
    assert assess_metric_query(good, contract).status == "supported"
    other = (
        "SELECT SUM(b.expense_budget), MAX(b.revenue_target) FROM monthly_budgets b"
        " WHERE b.month = DATE '2025-08-01'"
    )
    assert assess_metric_query(other, contract).status == "insufficient"


def test_time_column_must_match_the_new_metric():
    status = assess_metric_query(
        "SELECT SUM(amount) FROM expense_entries WHERE expense_date > DATE '2025-01-01'",
        _contract("expense_amount/v1", "sales_orders.order_date"),
    ).status
    assert status == "insufficient"


def test_unregistered_metric_is_still_refused():
    status = assess_metric_query(
        "SELECT SUM(amount) FROM expense_entries",
        _contract("made_up/v1", "expense_entries.expense_date"),
    ).status
    assert status == "irrelevant"
