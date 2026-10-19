"""Seed one disposable demo company database and provision its read-only role."""

from __future__ import annotations

import os

from psycopg import sql

from generate_business_data import (
    create_indexes,
    db_connection,
    recreate_schema,
    seed_dimensions,
    seed_transactions,
)


def seed_demo_business_data() -> None:
    """Use the deterministic business tables without writing a host knowledge corpus."""
    with db_connection() as connection, connection.cursor() as cursor:
        recreate_schema(cursor)
        employees, products, customers, suppliers = seed_dimensions(cursor)
        seed_transactions(cursor, employees, products, customers, suppliers)
        create_indexes(cursor)
        connection.commit()


def provision_readonly_role() -> None:
    """Grant only SELECT access after the deterministic schema is created."""
    role_name = os.environ["DEMO_READONLY_USER"]
    password = os.environ["DEMO_READONLY_PASSWORD"]
    company_label = os.environ["DEMO_COMPANY_LABEL"]
    with db_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        if cursor.fetchone() is None:
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(role_name))
            )
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(role_name), sql.Literal(password)
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(os.environ.get("BUSINESS_DB_NAME", "business_data")),
                sql.Identifier(role_name),
            )
        )
        cursor.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                sql.Identifier(role_name)
            )
        )
        cursor.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
                sql.Identifier(role_name)
            )
        )
        cursor.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}"
            ).format(sql.Identifier(role_name))
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS demo_company_identity (
                id SMALLINT PRIMARY KEY CHECK (id = 1),
                company_label TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO demo_company_identity (id, company_label)
            VALUES (1, %s)
            ON CONFLICT (id) DO UPDATE SET company_label = EXCLUDED.company_label
            """,
            (company_label,),
        )
        cursor.execute(
            sql.SQL("GRANT SELECT ON demo_company_identity TO {}").format(
                sql.Identifier(role_name)
            )
        )
        connection.commit()


def main() -> None:
    seed_demo_business_data()
    provision_readonly_role()
    print(f"Demo business database ready for {os.environ['DEMO_COMPANY_LABEL']}.")


if __name__ == "__main__":
    main()
