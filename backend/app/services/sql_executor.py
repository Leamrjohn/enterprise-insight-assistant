"""安全的只读SQL执行器"""

import logging
import re

import psycopg
from app.services.sql_validator import validate_sql

logger = logging.getLogger(__name__)

READONLY_CONFIG = {
    "host": "127.0.0.1",
    "port": 5434,
    "user": "business_readonly",
    "password": "readonly_password_123",
    "dbname": "business_data",
}


def execute_readonly_sql(
    sql: str,
    allowed_tables: set[str],
    max_rows: int = 1000,
    timeout_ms: int = 10000,
):
    """校验并执行只读SQL，返回 (列名列表, 行数据列表)"""
    # 1. 先校验SQL（复用你之前写的函数）
    validate_sql(sql, allowed_tables, set())

    # 2. 如果用户没加LIMIT，自动补一个
    if "LIMIT" not in sql.upper():
        sql = f"{sql.strip()} LIMIT {max_rows}"

    # 3. 连接数据库
    conn = psycopg.connect(**READONLY_CONFIG)
    cur = conn.cursor()

    try:
        # 4. 设置超时
        cur.execute(f"SET statement_timeout = {timeout_ms}")  # type: ignore[arg-type]

        # 5. 执行
        cur.execute(sql) # type: ignore[arg-type]
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] # type: ignore[arg-type]

        logger.info(
            "SQL executed",
            extra={
                "sql": sql,
                "row_count": len(rows),
                "timeout_ms": timeout_ms,
            },
        )

        # 6. 敏感字段脱敏
        SENSITIVE_PATTERNS = {
            "mobile": (re.compile(r"1[3-9]\d{9}"), lambda m: m[:3] + "****" + m[7:]),
        }

        masked_rows = []
        for row in rows:
            masked = list(row)
            for i, val in enumerate(masked):
                if isinstance(val, str):
                    for label, (pattern, mask_func) in SENSITIVE_PATTERNS.items():
                        if pattern.search(val):
                            masked[i] = pattern.sub(mask_func, val)
            masked_rows.append(tuple(masked))
        rows = masked_rows

        return columns, rows
    except Exception as e:
        logger.error(
            "SQL execution failed",
            extra={
                "sql": sql,
                "error": str(e),
            },
        )
        raise
    finally:
        cur.close()
        conn.close()
