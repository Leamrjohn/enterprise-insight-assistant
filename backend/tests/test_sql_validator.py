"""受控经营数据 SQL 校验器的规则测试。"""

import pytest

from app.tools.business_semantic_catalog import BUSINESS_TABLES
from app.tools.validator import validate_sql


ALLOWED_TABLES = set(BUSINESS_TABLES)


def validate(sql: str) -> None:
    validate_sql(sql, allowed_tables=ALLOWED_TABLES)


def test_allows_registered_tables_columns_and_join() -> None:
    validate(
        """
        SELECT o.total_amount, c.region_code
        FROM sales_orders AS o
        JOIN customers AS c ON o.customer_id = c.id
        WHERE o.status = 'delivered'
        """
    )


def test_allows_select_alias_only_in_order_by() -> None:
    validate(
        """
        SELECT
            DATE_TRUNC('month', o.order_date) AS month,
            SUM(o.total_amount) AS revenue
        FROM sales_orders AS o
        GROUP BY DATE_TRUNC('month', o.order_date)
        ORDER BY month
        """
    )


def test_allows_select_alias_in_group_by_and_order_by() -> None:
    validate(
        """
        SELECT
            EXTRACT(YEAR FROM o.order_date) AS yr,
            EXTRACT(MONTH FROM o.order_date) AS mon,
            SUM(o.total_amount) AS revenue
        FROM sales_orders AS o
        GROUP BY yr, mon
        ORDER BY yr, mon
        """
    )


def test_rejects_unknown_unqualified_order_by_name() -> None:
    with pytest.raises(ValueError, match="必须使用表名或表别名前缀"):
        validate(
            """
            SELECT SUM(o.total_amount) AS revenue
            FROM sales_orders AS o
            ORDER BY unknown_name
            """
        )


def test_rejects_non_select_statement() -> None:
    with pytest.raises(ValueError, match="仅允许SELECT"):
        validate("DELETE FROM sales_orders")


def test_rejects_multiple_statements() -> None:
    with pytest.raises(ValueError, match="不允许执行多条SQL语句"):
        validate("SELECT o.id FROM sales_orders AS o; DELETE FROM sales_orders")


def test_rejects_star() -> None:
    with pytest.raises(ValueError, match="不允许使用\\*"):
        validate("SELECT o.* FROM sales_orders AS o")


def test_rejects_cte() -> None:
    with pytest.raises(ValueError, match="暂不允许CTE"):
        validate(
            """
            WITH recent_orders AS (
                SELECT o.id FROM sales_orders AS o
            )
            SELECT r.id FROM recent_orders AS r
            """
        )


def test_rejects_subquery() -> None:
    with pytest.raises(ValueError, match="暂不允许子查询"):
        validate(
            """
            SELECT r.id
            FROM (
                SELECT o.id FROM sales_orders AS o
            ) AS r
            """
        )


def test_rejects_table_outside_business_catalogue() -> None:
    with pytest.raises(ValueError, match="不在业务目录"):
        validate("SELECT d.content FROM business_documents AS d")


def test_rejects_explicit_schema() -> None:
    with pytest.raises(ValueError, match="不允许指定数据库或Schema"):
        validate("SELECT t.question FROM evaluation.scenario_truth AS t")


def test_rejects_column_outside_table_catalogue() -> None:
    with pytest.raises(ValueError, match="不允许从表 'sales_orders' 查询"):
        validate("SELECT o.created_at FROM sales_orders AS o")


def test_rejects_unqualified_column() -> None:
    with pytest.raises(ValueError, match="必须使用表名或表别名前缀"):
        validate("SELECT total_amount FROM sales_orders")


def test_rejects_unregistered_join() -> None:
    with pytest.raises(ValueError, match="不允许的表关联"):
        validate(
            """
            SELECT o.total_amount, c.name
            FROM sales_orders AS o
            JOIN customers AS c ON o.id = c.id
            """
        )
