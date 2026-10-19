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
}


def get_metric_definition(reference: str | None) -> MetricDefinition | None:
    if not isinstance(reference, str):
        return None
    return METRIC_DEFINITIONS.get(reference)
