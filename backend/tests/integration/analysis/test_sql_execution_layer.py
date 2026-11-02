"""Execution-layer SQL defenses, tested with the AST validator switched off.

Stage 4.3 showed the AST layer once let 27 of 54 attacks through; the database
role and the read-only transaction were what stopped them.  These tests keep
that second line honest on its own: every attack is sent to the real demo
business database as ``acme_readonly`` with ``validate_sql`` bypassed.

Nothing here commits.  Write attempts run inside transactions that are rolled
back, so even a regression cannot change business data.

Needs the compose demo database (host port 5435/5436) and the
``ACME_DEMO_DATABASE_PASSWORD`` variable; the test module is skipped without it.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import psycopg
import pytest
from app.modules.analysis.data import sql_executor
from app.modules.organizations.models import BusinessDataSource
from psycopg import errors
from pydantic import SecretStr

CREDENTIAL_ENV = "ACME_DEMO_DATABASE_PASSWORD"
HOST = os.environ.get("BUSINESS_SECURITY_TEST_HOST", "localhost")
ACME_PORT = int(os.environ.get("BUSINESS_SECURITY_TEST_ACME_PORT", "5435"))
BETA_PORT = int(os.environ.get("BUSINESS_SECURITY_TEST_BETA_PORT", "5436"))
ROLE = "acme_readonly"
TABLE = "customers"

pytestmark = pytest.mark.skipif(
    not os.environ.get(CREDENTIAL_ENV),
    reason=f"{CREDENTIAL_ENV} is not set; demo business database unavailable",
)

WRITE_REJECTED = (errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege)


def _source() -> BusinessDataSource:
    return BusinessDataSource(
        dialect="postgresql",
        credential_env_var=CREDENTIAL_ENV,
        connection_config={
            "host": HOST,
            "port": ACME_PORT,
            "database": "acme_business",
            "user": ROLE,
        },
    )


def _connect(*, port: int = ACME_PORT, dbname: str = "acme_business", **kwargs):
    return psycopg.connect(
        host=HOST,
        port=port,
        dbname=dbname,
        user=ROLE,
        password=os.environ[CREDENTIAL_ENV],
        connect_timeout=5,
        **kwargs,
    )


@pytest.fixture
def unvalidated(monkeypatch):
    """Run the real executor as if the AST layer had approved everything."""
    monkeypatch.setattr(sql_executor, "validate_sql", lambda *_a, **_k: None)

    def run(sql: str, *, timeout_ms: int = 2_000):
        return sql_executor.execute_readonly_sql(
            sql, {TABLE}, timeout_ms=timeout_ms, data_source=_source()
        )

    return run


def test_executor_still_answers_a_normal_query(unvalidated):
    columns, rows = unvalidated(f"SELECT count(*) AS n FROM {TABLE}")

    assert columns == ["n"]
    assert rows[0][0] > 0


# Attacks the AST layer used to miss (stage 4.3), now sent past it on purpose.
EXECUTOR_ATTACKS = {
    "cte_delete": f"WITH d AS (DELETE FROM {TABLE} RETURNING 1) SELECT * FROM d",
    "cte_update": (
        f"WITH u AS (UPDATE {TABLE} SET id = id RETURNING 1) SELECT * FROM u"
    ),
    "cte_insert": (
        f"WITH i AS (INSERT INTO {TABLE} SELECT * FROM {TABLE} LIMIT 0 RETURNING 1)"
        " SELECT * FROM i"
    ),
    "for_update": f"SELECT id FROM {TABLE} LIMIT 1 FOR UPDATE",
    "for_share": f"SELECT id FROM {TABLE} LIMIT 1 FOR SHARE",
    "select_into": f"SELECT * INTO stolen_copy FROM {TABLE}",
}


@pytest.mark.parametrize("name", sorted(EXECUTOR_ATTACKS))
def test_write_and_lock_attacks_fail_inside_the_executor(unvalidated, name):
    with pytest.raises(WRITE_REJECTED):
        unvalidated(EXECUTOR_ATTACKS[name])


@pytest.mark.parametrize(
    ("name", "sql", "expected"),
    [
        ("pg_read_file", "SELECT pg_read_file('/etc/passwd')", WRITE_REJECTED),
        ("pg_ls_dir", "SELECT pg_ls_dir('/')", WRITE_REJECTED),
        ("lo_import", "SELECT lo_import('/etc/passwd')", WRITE_REJECTED),
        (
            "dblink",
            "SELECT * FROM dblink('dbname=postgres', 'SELECT 1') AS t(x int)",
            (errors.UndefinedFunction,),
        ),
    ],
)
def test_server_side_functions_are_unavailable(unvalidated, name, sql, expected):
    with pytest.raises(expected):
        unvalidated(sql)


def test_statement_timeout_cancels_a_slow_query(unvalidated):
    with pytest.raises(errors.QueryCanceled):
        unvalidated("SELECT pg_sleep(3)", timeout_ms=300)


def test_query_cannot_lift_its_own_timeout_mid_statement(unvalidated):
    """The timer starts with the statement, so raising the GUC inside it is moot."""
    with pytest.raises(errors.QueryCanceled):
        unvalidated(
            "SELECT set_config('statement_timeout', '0', false), pg_sleep(3)",
            timeout_ms=300,
        )


def test_executor_session_is_read_only():
    with (
        _connect(options="-c default_transaction_read_only=on") as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SHOW default_transaction_read_only")
        assert cur.fetchone()[0] == "on"
        with pytest.raises(errors.ReadOnlySqlTransaction):
            cur.execute("CREATE TEMP TABLE scratch (x int)")
        conn.rollback()


def test_role_attributes_grant_no_escape():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication"
            " FROM pg_roles WHERE rolname = current_user"
        )
        assert cur.fetchone() == (False, False, False, False, False)
        cur.execute(
            "SELECT count(*) FROM pg_auth_members m"
            " JOIN pg_roles r ON r.oid = m.roleid"
            " JOIN pg_roles u ON u.oid = m.member"
            " WHERE u.rolname = current_user"
            " AND r.rolname IN ('pg_read_server_files', 'pg_write_server_files',"
            " 'pg_execute_server_program', 'pg_write_all_data', 'pg_signal_backend')"
        )
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT has_schema_privilege('public', 'CREATE')")
        assert cur.fetchone()[0] is False


def test_role_has_no_write_privilege_on_any_business_table():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FILTER (WHERE has_table_privilege(c.oid,"
            " 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')), count(*)"
            " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')"
        )
        writable, total = cur.fetchone()
        assert total > 0
        assert writable == 0


@pytest.mark.parametrize(
    "sql",
    [
        f"INSERT INTO {TABLE} SELECT * FROM {TABLE} LIMIT 0",
        f"UPDATE {TABLE} SET id = id WHERE false",
        f"DELETE FROM {TABLE} WHERE false",
        f"TRUNCATE {TABLE}",
        "CREATE TABLE public.stolen (x int)",
        f"ALTER TABLE {TABLE} ADD COLUMN pwned int",
        "COPY (SELECT 1) TO PROGRAM 'id'",
        f"ALTER ROLE {ROLE} SUPERUSER",
    ],
)
def test_role_refuses_writes_even_in_a_read_write_transaction(sql):
    """Layer independence: without the read-only session the role alone still holds."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ WRITE")
        with pytest.raises(errors.InsufficientPrivilege):
            cur.execute(sql)
        conn.rollback()


def test_acme_credentials_cannot_reach_another_tenant_server():
    with pytest.raises(psycopg.OperationalError):
        _connect(port=BETA_PORT, dbname="beta_business")


def test_connection_lands_on_the_acme_tenant(unvalidated):
    _, rows = unvalidated("SELECT company_label FROM demo_company_identity")

    assert len(rows) == 1
    assert "acme" in rows[0][0].lower()


@pytest.fixture
def registered_query(monkeypatch):
    """Point the template-query path at the demo database under the same contract."""
    monkeypatch.setattr(
        sql_executor,
        "get_settings",
        lambda: SimpleNamespace(
            business_database_host=HOST,
            business_database_port=ACME_PORT,
            business_database_name="acme_business",
            business_database_user=ROLE,
            business_database_password=SecretStr(os.environ[CREDENTIAL_ENV]),
        ),
    )
    return sql_executor.execute_registered_readonly_query


def test_registered_query_runs_in_a_read_only_transaction(registered_query):
    _, rows = registered_query("SELECT current_setting('transaction_read_only')", {})

    assert rows == [("on",)]


def test_registered_query_write_is_stopped_by_the_transaction_not_only_the_role(
    registered_query,
):
    """ReadOnlySqlTransaction proves this layer works; a privilege error would not."""
    with pytest.raises(errors.ReadOnlySqlTransaction):
        registered_query(
            f"WITH d AS (DELETE FROM {TABLE} WHERE false RETURNING 1) SELECT * FROM d",
            {},
        )


def test_registered_query_still_binds_parameters_and_times_out(registered_query):
    _, rows = registered_query("SELECT %(n)s::int + 1", {"n": 1})
    assert rows == [(2,)]

    with pytest.raises(errors.QueryCanceled):
        registered_query("SELECT pg_sleep(3)", {}, timeout_ms=300)
