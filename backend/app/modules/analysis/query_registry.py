from dataclasses import dataclass
from typing import Any

from app.modules.analysis.data_request import DataRequest


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    parameters: dict[str, Any]
    allowed_tables: frozenset[str]


REGIONAL_REVENUE_COMPARISON_SQL = """
WITH monthly_revenue AS (
    SELECT
        c.region_code,
        COALESCE(
            SUM(o.total_amount) FILTER (
                WHERE o.order_date >= %(current_month)s
                  AND o.order_date < %(current_month)s + INTERVAL '1 month'
            ),
            0
        ) AS current_revenue,
        COALESCE(
            SUM(o.total_amount) FILTER (
                WHERE o.order_date >= %(comparison_month)s
                  AND o.order_date < %(comparison_month)s + INTERVAL '1 month'
            ),
            0
        ) AS comparison_revenue
    FROM sales_orders AS o
    JOIN customers AS c ON c.id = o.customer_id
    WHERE o.status = 'delivered'
      AND o.order_date >= LEAST(
          %(current_month)s,
          %(comparison_month)s
      )
      AND o.order_date < GREATEST(
          %(current_month)s,
          %(comparison_month)s
      ) + INTERVAL '1 month'
      AND (%(region)s IS NULL OR c.region_code = %(region)s)
    GROUP BY c.region_code
)
SELECT
    region_code,
    current_revenue,
    comparison_revenue,
    current_revenue - comparison_revenue AS revenue_change,
    CASE
        WHEN comparison_revenue = 0 THEN NULL
        ELSE ROUND(
            (current_revenue - comparison_revenue)
            / comparison_revenue * 100,
            2
        )
    END AS revenue_change_rate
FROM monthly_revenue
ORDER BY revenue_change ASC NULLS LAST
LIMIT %(limit)s
"""


def compile_business_query(request: DataRequest) -> CompiledQuery:
    if request.query_id != "regional_revenue_comparison":
        raise ValueError(f"Query is not implemented: {request.query_id}")

    return CompiledQuery(
        sql=REGIONAL_REVENUE_COMPARISON_SQL,
        parameters={
            "current_month": request.current_month,
            "comparison_month": request.comparison_month,
            "region": request.region,
            "limit": request.limit,
        },
        allowed_tables=frozenset({"customers", "sales_orders"}),
    )
