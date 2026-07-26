"""Tenant schema snapshots must constrain generated SQL before execution."""

import pytest

from app.tools.snapshot_catalog import SnapshotCatalog
from app.tools.validator import validate_sql


CATALOG = SnapshotCatalog.from_snapshot(
    {
        "tables": {
            "inventory_balances": [
                {"name": "product_id"},
                {"name": "on_hand"},
            ],
            "products": [
                {"name": "id"},
                {"name": "sku"},
            ],
        },
        "joins": [
            {
                "left_table": "inventory_balances",
                "left_column": "product_id",
                "right_table": "products",
                "right_column": "id",
            }
        ],
    }
)


def validate(sql: str) -> None:
    validate_sql(sql, allowed_tables=set(CATALOG.tables), catalog=CATALOG)


def test_allows_discovered_table_columns_and_foreign_key_join() -> None:
    validate(
        """
        SELECT i.on_hand, p.sku
        FROM inventory_balances AS i
        JOIN products AS p ON i.product_id = p.id
        """
    )


def test_rejects_column_not_present_in_company_snapshot() -> None:
    with pytest.raises(ValueError, match="不允许从表 'inventory_balances' 查询"):
        validate("SELECT i.unit_cost FROM inventory_balances AS i")


def test_rejects_join_not_declared_by_company_foreign_key() -> None:
    with pytest.raises(ValueError, match="不允许的表关联"):
        validate(
            """
            SELECT i.on_hand, p.sku
            FROM inventory_balances AS i
            JOIN products AS p ON i.on_hand = p.id
            """
        )


def test_rejects_table_not_present_in_company_snapshot() -> None:
    with pytest.raises(ValueError, match="不在当前公司数据目录中"):
        validate("SELECT o.total_amount FROM sales_orders AS o")
