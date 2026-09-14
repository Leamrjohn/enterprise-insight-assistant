"""安全的只读SQL执行器"""

import logging
import os
import re
from typing import LiteralString, TypedDict, cast

import psycopg
from psycopg import sql as psycopg_sql
from app.core.settings import get_settings
from app.modules.organizations.models import BusinessDataSource
from app.modules.analysis.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.sql_validator import validate_sql

logger = logging.getLogger(__name__)


def _apply_row_limit(sql: str, max_rows: int) -> str:
    """Add the safety limit without turning a valid trailing semicolon invalid."""
    normalized_sql = sql.strip()
    if "LIMIT" in normalized_sql.upper():
        return normalized_sql

    return f"{normalized_sql.rstrip(';').rstrip()} LIMIT {max_rows}"


def _mask_sensitive_rows(rows):
    """对两个只读执行路径使用同一套展示脱敏规则。"""
    sensitive_patterns = {
        "mobile": (re.compile(r"1[3-9]\d{9}"), lambda m: m[:3] + "****" + m[7:]),
    }

    masked_rows = []
    for row in rows:
        masked = list(row)
        for index, value in enumerate(masked):
            if isinstance(value, str):
                for pattern, mask_func in sensitive_patterns.values():
                    if pattern.search(value):
                        masked[index] = pattern.sub(mask_func, value)
        masked_rows.append(tuple(masked))
    return masked_rows


def execute_registered_readonly_query(
    sql: str,
    parameters: dict,
    *,
    timeout_ms: int = 10000,
):
    """执行代码仓库中登记的参数化只读查询，不接受外部 SQL。"""
    settings = get_settings()
    conn = psycopg.connect(
        host=settings.business_database_host,
        port=settings.business_database_port,
        dbname=settings.business_database_name,
        user=settings.business_database_user,
        password=settings.business_database_password.get_secret_value(),
    )
    cur = conn.cursor()

    try:
        cur.execute(
            psycopg_sql.SQL("SET statement_timeout = {}").format(
                psycopg_sql.Literal(timeout_ms)
            )
        )
        cur.execute(psycopg_sql.SQL(cast(LiteralString, sql)), parameters)
        rows = cur.fetchall()
        description = cur.description
        columns = [desc[0] for desc in description] if description is not None else []
        logger.info(
            "Registered business query executed",
            extra={"row_count": len(rows), "timeout_ms": timeout_ms},
        )
        return columns, _mask_sensitive_rows(rows)
    except Exception:
        logger.exception("Registered business query execution failed")
        raise
    finally:
        cur.close()
        conn.close()


def execute_readonly_sql(
    sql: str,
    allowed_tables: set[str],
    max_rows: int = 1000,
    timeout_ms: int = 10000,
    *,
    catalog: SnapshotCatalog | None = None,
    data_source: BusinessDataSource | None = None,
):
    """校验并执行只读SQL，返回 (列名列表, 行数据列表)"""
    validate_sql(sql, allowed_tables, catalog=catalog)
    # 如果用户没加 LIMIT，自动补一个。模型常会输出单个结尾分号，
    # 必须先移除它，否则会形成无效的 "...; LIMIT n"。
    sql = _apply_row_limit(sql, max_rows)

    connection = _connection_details(data_source)
    conn = psycopg.connect(
        host=connection["host"],
        port=connection["port"],
        dbname=connection["dbname"],
        user=connection["user"],
        password=connection["password"],
        options="-c default_transaction_read_only=on",
    )
    cur = conn.cursor()

    try:
        cur.execute("SET TRANSACTION READ ONLY")
        # 4. 设置超时
        cur.execute(
            psycopg_sql.SQL("SET statement_timeout = {}").format(
                psycopg_sql.Literal(timeout_ms)
            )
        )

        # 5. 执行
        cur.execute(psycopg_sql.SQL(cast(LiteralString, sql)))
        rows = cur.fetchall()
        description = cur.description
        columns = [desc[0] for desc in description] if description is not None else []

        logger.info(
            "SQL executed",
            extra={
                "sql": sql,
                "row_count": len(rows),
                "timeout_ms": timeout_ms,
            },
        )

        return columns, _mask_sensitive_rows(rows)
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


class _ConnectionDetails(TypedDict):
    host: str
    port: int
    dbname: str
    user: str
    password: str


def _connection_details(
    data_source: BusinessDataSource | None,
) -> _ConnectionDetails:
    """Resolve a tenant source without persisting or logging its password."""
    if data_source is None:
        settings = get_settings()
        return {
            "host": settings.business_database_host,
            "port": settings.business_database_port,
            "dbname": settings.business_database_name,
            "user": settings.business_database_user,
            "password": settings.business_database_password.get_secret_value(),
        }

    if data_source.dialect != "postgresql":
        raise ValueError("当前数据源不是受支持的 PostgreSQL 数据库")
    password = os.environ.get(data_source.credential_env_var)
    if not password:
        raise ValueError("配置的数据源凭据不可用")
    config = data_source.connection_config
    return {
        "host": config["host"],
        "port": config["port"],
        "dbname": config["database"],
        "user": config["user"],
        "password": password,
    }
