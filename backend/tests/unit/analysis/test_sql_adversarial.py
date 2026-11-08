"""Stage 4.4: the AST layer must reject every attack on its own.

Execution-layer controls (read-only role, read-only transaction, timeouts) are
tested separately; this suite assumes they could be bypassed.
"""

import json
from pathlib import Path

import pytest
from app.modules.analysis.catalog.semantic_catalog import BUSINESS_TABLES
from app.modules.analysis.data.sql_validator import validate_sql

# Production validates against the company schema snapshot, which also has `regions`.
ALLOWED = set(BUSINESS_TABLES) | {"regions"}
T = "customers"


class _SnapshotTables:
    def has_table(self, name: str) -> bool:
        return name in ALLOWED


CATALOG = _SnapshotTables()

ATTACKS = {
    # Statement kind and multiple statements
    "delete": f"DELETE FROM {T}",
    "update": f"UPDATE {T} SET name = 'x'",
    "insert": f"INSERT INTO {T} (id) VALUES (1)",
    "drop": f"DROP TABLE {T}",
    "truncate": f"TRUNCATE {T}",
    "multi_statement": f"SELECT 1 FROM {T}; DROP TABLE {T}",
    "multi_statement_comment": f"SELECT 1 FROM {T}; -- \nDELETE FROM {T}",
    "lowercase_delete": f"delete from {T}",
    "mixed_case_drop": f"DrOp TaBlE {T}",
    "copy_to_program": f"COPY {T} TO PROGRAM 'id'",
    "grant": f"GRANT ALL ON {T} TO public",
    "set_role": "SET ROLE postgres",
    "create_function": "CREATE FUNCTION f() RETURNS int AS 'select 1' LANGUAGE sql",
    "do_block": "DO $$ BEGIN PERFORM 1; END $$",
    # Writes hidden inside SELECT
    "cte_delete": f"WITH d AS (DELETE FROM {T} RETURNING *) SELECT * FROM d",
    "cte_update": f"WITH u AS (UPDATE {T} SET name='x' RETURNING id) SELECT * FROM u",
    "cte_insert": f"WITH i AS (INSERT INTO {T} (id) VALUES (1) RETURNING id) SELECT * FROM i",
    "select_into": f"SELECT * INTO stolen FROM {T}",
    # Locks
    "for_update": f"SELECT * FROM {T} FOR UPDATE",
    "for_share": f"SELECT * FROM {T} FOR SHARE",
    "for_no_key_update": f"SELECT * FROM {T} FOR NO KEY UPDATE",
    # Side-effect and file/network functions
    "pg_sleep": f"SELECT pg_sleep(30) FROM {T}",
    "pg_sleep_upper": f"SELECT PG_SLEEP(30) FROM {T}",
    "pg_read_file": f"SELECT pg_read_file('/etc/passwd') FROM {T}",
    "pg_read_binary_file": f"SELECT pg_read_binary_file('/etc/passwd') FROM {T}",
    "pg_ls_dir": f"SELECT pg_ls_dir('.') FROM {T}",
    "pg_stat_file": f"SELECT pg_stat_file('postgresql.conf') FROM {T}",
    "lo_import": f"SELECT lo_import('/etc/passwd') FROM {T}",
    "lo_export": f"SELECT lo_export(1, '/tmp/x') FROM {T}",
    "set_config": f"SELECT set_config('statement_timeout', '0', false) FROM {T}",
    "current_setting": f"SELECT current_setting('data_directory') FROM {T}",
    "pg_terminate_backend": f"SELECT pg_terminate_backend(1) FROM {T}",
    "pg_cancel_backend": f"SELECT pg_cancel_backend(1) FROM {T}",
    "pg_advisory_lock": f"SELECT pg_advisory_lock(1) FROM {T}",
    "dblink": f"SELECT dblink('host=evil', 'select 1') FROM {T}",
    "dblink_exec": f"SELECT dblink_exec('host=evil', 'drop table x') FROM {T}",
    "function_in_where": f"SELECT id FROM {T} WHERE pg_sleep(5) IS NOT NULL",
    "function_in_subquery": f"SELECT id FROM {T} WHERE id IN (SELECT pg_sleep(5))",
    "function_in_cte": f"WITH s AS (SELECT pg_sleep(5) AS x) SELECT * FROM {T}, s",
    "function_in_order_by": f"SELECT id FROM {T} ORDER BY pg_sleep(1)",
    "query_to_xml": f"SELECT query_to_xml('select 1', true, true, '') FROM {T}",
    "txid_current": f"SELECT txid_current() FROM {T}",
    # Scope escapes
    "schema_qualified_catalog": "SELECT * FROM pg_catalog.pg_user",
    "schema_qualified_info": "SELECT * FROM information_schema.tables",
    "bare_system_table": "SELECT * FROM pg_shadow",
    "bare_pg_roles": "SELECT * FROM pg_roles",
    "unknown_table": "SELECT * FROM salaries",
    "table_in_subquery": f"SELECT * FROM {T} WHERE id IN (SELECT usesysid FROM pg_user)",
    "table_in_join": f"SELECT * FROM {T} JOIN pg_authid ON true",
    "cross_database": f"SELECT * FROM other_db.public.{T}",
    "no_table_constant": "SELECT 1",
    "no_table_version": "SELECT version()",
    # Malformed
    "empty": "",
    "garbage": "SELEC * FRM",
}


@pytest.mark.parametrize("name", sorted(ATTACKS))
def test_ast_layer_rejects_attack(name: str) -> None:
    with pytest.raises(ValueError):
        validate_sql(ATTACKS[name], ALLOWED, catalog=CATALOG)


def test_attack_suite_covers_at_least_fifty_cases() -> None:
    assert len(ATTACKS) >= 50


HISTORICAL = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "fixtures/sql/historical_generated_sql.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize("index", range(len(HISTORICAL)))
def test_historical_model_sql_is_still_accepted(index: int) -> None:
    """False-positive guard: every SQL the model generated in past runs stays valid."""
    validate_sql(HISTORICAL[index], ALLOWED, catalog=CATALOG)
