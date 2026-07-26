"""Read PostgreSQL metadata into a tenant-scoped query catalog."""

from __future__ import annotations

import hashlib
import json
import os

import psycopg

from app.models.company import BusinessDataSource


def discover_postgres_schema(source: BusinessDataSource) -> tuple[dict, str]:
    if source.dialect != "postgresql":
        raise ValueError("Only PostgreSQL discovery is supported")
    password = os.environ.get(source.credential_env_var)
    if not password:
        raise ValueError("Configured database credential is unavailable")
    config = source.connection_config
    schema = config["schema"]
    with psycopg.connect(
        host=config["host"],
        port=config["port"],
        dbname=config["database"],
        user=config["user"],
        password=password,
        connect_timeout=5,
        options="-c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s
                ORDER BY table_name, ordinal_position
                """,
                (schema,),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT
                    child_table.relname AS left_table,
                    child_column.attname AS left_column,
                    parent_table.relname AS right_table,
                    parent_column.attname AS right_column
                FROM pg_catalog.pg_constraint AS foreign_key
                JOIN pg_catalog.pg_class AS child_table
                  ON child_table.oid = foreign_key.conrelid
                JOIN pg_catalog.pg_namespace AS child_namespace
                  ON child_namespace.oid = child_table.relnamespace
                JOIN pg_catalog.pg_class AS parent_table
                  ON parent_table.oid = foreign_key.confrelid
                JOIN pg_catalog.pg_attribute AS child_column
                  ON child_column.attrelid = child_table.oid
                 AND child_column.attnum = foreign_key.conkey[1]
                JOIN pg_catalog.pg_attribute AS parent_column
                  ON parent_column.attrelid = parent_table.oid
                 AND parent_column.attnum = foreign_key.confkey[1]
                WHERE foreign_key.contype = 'f'
                  AND child_namespace.nspname = %s
                  AND array_length(foreign_key.conkey, 1) = 1
                  AND array_length(foreign_key.confkey, 1) = 1
                ORDER BY child_table.relname, child_column.attname
                """,
                (schema,),
            )
            join_rows = cursor.fetchall()
    tables: dict[str, list[dict]] = {}
    for table_name, column_name, data_type, is_nullable in rows:
        tables.setdefault(table_name, []).append(
            {"name": column_name, "type": data_type, "nullable": is_nullable == "YES"}
        )
    catalog = {
        "dialect": "postgresql",
        "schema": schema,
        "tables": tables,
        "joins": [
            {
                "left_table": left_table,
                "left_column": left_column,
                "right_table": right_table,
                "right_column": right_column,
            }
            for left_table, left_column, right_table, right_column in join_rows
        ],
    }
    encoded = json.dumps(catalog, ensure_ascii=False, sort_keys=True).encode()
    return catalog, hashlib.sha256(encoded).hexdigest()
