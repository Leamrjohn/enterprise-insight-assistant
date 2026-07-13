"""测试 SQL 安全校验器"""
import pytest
from app.tools.validator import validate_sql

# 定义白名单（和业务库中的表一致）
ALLOWED_TABLES = {"customers", "products", "orders", "order_items", "complaints"}

def test_valid_select_passes():
    validate_sql(
        "SELECT * FROM  orders",
        allowed_tables= ALLOWED_TABLES,
        allowed_columns= set(),
    )
def test_delete_rejected():
    with pytest.raises(ValueError,match="仅允许SELECT"):
        validate_sql(
            "DELETE FROM orders WHERE id = 1",
            allowed_tables= ALLOWED_TABLES,
            allowed_columns= set(),
        )
def test_multiple_statements_rejected():
    with pytest.raises(ValueError, match="不允许执行多条SQL语句"):
        validate_sql(
            "SELECT * FROM orders; DELETE FROM orders",
            allowed_tables=ALLOWED_TABLES,
            allowed_columns=set(),
        )
def test_table_not_in_whitelist_rejected():
    with pytest.raises(ValueError,match="不在白名单"):
        validate_sql(
            "SELECT * FROM oredews ",
            allowed_tables=ALLOWED_TABLES,
            allowed_columns= set(),
        )
