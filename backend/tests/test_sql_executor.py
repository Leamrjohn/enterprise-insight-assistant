from app.tools.executor import _apply_row_limit, execute_readonly_sql


ALLOWED_TABLES = {"customers", "products", "orders", "order_items", "complaints"}


def test_execute_select_returns_data():
    columns, rows = execute_readonly_sql(
        "SELECT * FROM orders LIMIT 3",
        allowed_tables=ALLOWED_TABLES,
    )
    assert len(columns) == 4
    assert len(rows) == 3
    assert rows[0] is not None


def test_auto_limit_applied():
    columns, rows = execute_readonly_sql(
        "SELECT * FROM orders",
        allowed_tables=ALLOWED_TABLES,
        max_rows=5,
    )
    assert len(rows) <= 5


def test_auto_limit_handles_a_single_trailing_semicolon():
    assert _apply_row_limit("SELECT orders.id FROM orders;", 5) == (
        "SELECT orders.id FROM orders LIMIT 5"
    )


def test_existing_limit_is_preserved_with_a_trailing_semicolon():
    assert _apply_row_limit("SELECT orders.id FROM orders LIMIT 3;", 5) == (
        "SELECT orders.id FROM orders LIMIT 3;"
    )


def test_invalid_sql_rejected():
    try:
        execute_readonly_sql("DELETE FROM orders", allowed_tables=ALLOWED_TABLES)
        assert False
    except ValueError as e:
        assert "仅允许SELECT" in str(e)
