from app.modules.analysis.semantic_catalog import (
    FILTER_VALUE_DEFINITIONS,
    allowed_columns,
    is_allowed_join,
    is_allowed_table,
)


def test_allows_catalogued_table() -> None:
    assert is_allowed_table("sales_orders")


def test_rejects_table_outside_catalogue() -> None:
    assert not is_allowed_table("business_documents")
    assert not is_allowed_table("evaluation.scenario_truth")


def test_returns_only_allowed_columns() -> None:
    columns = allowed_columns("sales_orders")

    assert "total_amount" in columns
    assert "customer_id" in columns
    assert "created_at" not in columns


def test_returns_empty_columns_for_unknown_table() -> None:
    assert allowed_columns("unknown_table") == frozenset()


def test_allows_registered_join_in_both_directions() -> None:
    assert is_allowed_join(
        "sales_orders",
        "customer_id",
        "customers",
        "id",
    )
    assert is_allowed_join(
        "customers",
        "id",
        "sales_orders",
        "customer_id",
    )


def test_rejects_unregistered_join() -> None:
    assert not is_allowed_join(
        "payments",
        "invoice_id",
        "customers",
        "id",
    )


def test_records_database_codes_for_business_filter_values() -> None:
    region_values = FILTER_VALUE_DEFINITIONS["customers.region_code"]

    assert region_values["EAST"] == "华东"
    assert region_values["WEST"] == "西部"
    assert FILTER_VALUE_DEFINITIONS["sales_orders.status"]["delivered"]
