"""Versioned metric definitions for the managed demonstration business source.

Schema discovery can tell us a column exists.  It cannot tell us what that
column means, which filters are mandatory, or what unit it carries.  Those
facts live here as reviewed, source-controlled product configuration.
"""

from dataclasses import dataclass
from typing import Literal

MetricUnit = Literal["CNY", "count"]


@dataclass(frozen=True)
class MetricDefinition:
    reference: str
    display_name: str
    unit: MetricUnit
    source_columns: frozenset[str]
    aggregate_source_column: str
    aggregate_function: Literal["SUM", "COUNT"]
    time_column: str
    time_semantics: Literal["business_calendar_date"]
    mandatory_equals: tuple[tuple[str, str], ...] = ()
    rounding_scale: int = 0
    zero_denominator_policy: Literal["not_applicable", "insufficient"] = (
        "not_applicable"
    )
    # Accepted spellings when the aggregate argument is a formula, not one column.
    aggregate_expressions: tuple[str, ...] = ()

    @property
    def aggregate_display(self) -> str:
        argument = (
            self.aggregate_expressions[0]
            if self.aggregate_expressions
            else self.aggregate_source_column
        )
        return f"{self.aggregate_function}({argument})"


_LINE_AMOUNT = "sales_order_items.line_amount"
_UNIT_COST = "sales_order_items.unit_cost"
_QUANTITY = "sales_order_items.quantity"

METRIC_DEFINITIONS = {
    "revenue/v1": MetricDefinition(
        reference="revenue/v1",
        display_name="销售额",
        unit="CNY",
        source_columns=frozenset(
            {
                "sales_orders.total_amount",
                "sales_orders.order_date",
                "sales_orders.status",
            }
        ),
        aggregate_source_column="sales_orders.total_amount",
        aggregate_function="SUM",
        time_column="sales_orders.order_date",
        time_semantics="business_calendar_date",
        mandatory_equals=(("sales_orders.status", "delivered"),),
        rounding_scale=2,
    ),
    "ticket_count/v1": MetricDefinition(
        reference="ticket_count/v1",
        display_name="客诉数量",
        unit="count",
        source_columns=frozenset(
            {
                "service_tickets.id",
                "service_tickets.opened_date",
            }
        ),
        aggregate_source_column="service_tickets.id",
        aggregate_function="COUNT",
        time_column="service_tickets.opened_date",
        time_semantics="business_calendar_date",
    ),
    "delivered_order_count/v1": MetricDefinition(
        reference="delivered_order_count/v1",
        display_name="已交付订单数",
        unit="count",
        source_columns=frozenset(
            {
                "sales_orders.id",
                "sales_orders.order_date",
                "sales_orders.status",
            }
        ),
        aggregate_source_column="sales_orders.id",
        aggregate_function="COUNT",
        time_column="sales_orders.order_date",
        time_semantics="business_calendar_date",
        mandatory_equals=(("sales_orders.status", "delivered"),),
    ),
    "gross_profit/v1": MetricDefinition(
        reference="gross_profit/v1",
        display_name="毛利",
        unit="CNY",
        source_columns=frozenset(
            {
                "sales_order_items.line_amount",
                "sales_order_items.unit_cost",
                "sales_order_items.quantity",
                "sales_orders.order_date",
                "sales_orders.status",
            }
        ),
        aggregate_source_column="sales_order_items.line_amount",
        aggregate_function="SUM",
        time_column="sales_orders.order_date",
        time_semantics="business_calendar_date",
        mandatory_equals=(("sales_orders.status", "delivered"),),
        rounding_scale=2,
        aggregate_expressions=(
            f"{_LINE_AMOUNT} - {_UNIT_COST} * {_QUANTITY}",
            f"{_LINE_AMOUNT} - {_QUANTITY} * {_UNIT_COST}",
            f"{_LINE_AMOUNT} - ({_UNIT_COST} * {_QUANTITY})",
            f"{_LINE_AMOUNT} - ({_QUANTITY} * {_UNIT_COST})",
        ),
    ),
    "expense_amount/v1": MetricDefinition(
        reference="expense_amount/v1",
        display_name="费用金额",
        unit="CNY",
        source_columns=frozenset(
            {"expense_entries.amount", "expense_entries.expense_date"}
        ),
        aggregate_source_column="expense_entries.amount",
        aggregate_function="SUM",
        time_column="expense_entries.expense_date",
        time_semantics="business_calendar_date",
        rounding_scale=2,
    ),
    "revenue_target/v1": MetricDefinition(
        reference="revenue_target/v1",
        display_name="收入目标",
        unit="CNY",
        source_columns=frozenset(
            {"monthly_budgets.revenue_target", "monthly_budgets.month"}
        ),
        aggregate_source_column="monthly_budgets.revenue_target",
        aggregate_function="SUM",
        time_column="monthly_budgets.month",
        time_semantics="business_calendar_date",
        rounding_scale=2,
    ),
}


def get_metric_definition(reference: str | None) -> MetricDefinition | None:
    if not isinstance(reference, str):
        return None
    return METRIC_DEFINITIONS.get(reference)
