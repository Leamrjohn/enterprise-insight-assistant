"""A11b: tenant data sources only reach platform-registered, company-bound connections."""

import pytest
from app.modules.analysis.catalog import schema_discovery
from app.modules.analysis.data import sql_executor
from app.modules.organizations.connections import (
    ConnectionNotAllowed,
    new_connection,
    resolve_connection,
)
from app.modules.organizations.models import BusinessDataSource, PlatformDataConnection

ACME = 1
BETA = 2


def _connection(company_id=ACME, **overrides) -> PlatformDataConnection:
    fields = {
        "company_id": company_id,
        "name": "acme-demo",
        "host": "demo_business_acme",
        "port": 5432,
        "database": "acme_business",
        "username": "acme_readonly",
        "schema_name": "public",
        "credential_ref": "env:ACME_DEMO_DATABASE_PASSWORD",
        "status": "active",
        "created_by_operator": "test",
    }
    return PlatformDataConnection(**{**fields, **overrides})


def _source(company_id=ACME, connection=None) -> BusinessDataSource:
    return BusinessDataSource(
        company_id=company_id,
        name="tenant-db",
        dialect="postgresql",
        connection_config={},
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        connection=connection,
    )


@pytest.fixture(autouse=True)
def _demo_password(monkeypatch):
    monkeypatch.setenv("ACME_DEMO_DATABASE_PASSWORD", "acme-demo-password")


def _fail_connect(**_kwargs):
    raise AssertionError("must not connect")


def test_resolve_returns_the_registered_connection():
    details = resolve_connection(_source(connection=_connection()))

    assert details == {
        "host": "demo_business_acme",
        "port": 5432,
        "dbname": "acme_business",
        "user": "acme_readonly",
        "schema": "public",
        "password": "acme-demo-password",
    }


def test_resolve_refuses_a_source_without_a_platform_connection():
    with pytest.raises(ConnectionNotAllowed, match="not bound"):
        resolve_connection(_source(connection=None))


def test_resolve_refuses_another_companys_connection():
    # Beta's source points at Acme's legitimately registered connection.
    with pytest.raises(ConnectionNotAllowed, match="another company") as refused:
        resolve_connection(_source(company_id=BETA, connection=_connection(ACME)))

    assert "acme-demo-password" not in str(refused.value)


def test_resolve_refuses_an_inactive_connection():
    with pytest.raises(ConnectionNotAllowed, match="not active"):
        resolve_connection(_source(connection=_connection(status="disabled")))


def test_resolve_refuses_an_unknown_credential_scheme():
    with pytest.raises(ConnectionNotAllowed, match="credential"):
        resolve_connection(
            _source(connection=_connection(credential_ref="vault:acme/password"))
        )


def test_resolve_still_applies_the_a11a_policy(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "platform-signing-key")
    with pytest.raises(ValueError) as refused:
        resolve_connection(
            _source(connection=_connection(credential_ref="env:JWT_SECRET"))
        )

    assert "platform-signing-key" not in str(refused.value)


def test_sql_execution_refuses_another_companys_connection_before_connecting(
    monkeypatch,
):
    monkeypatch.setattr(sql_executor.psycopg, "connect", _fail_connect)
    with pytest.raises(ConnectionNotAllowed):
        sql_executor._connection_details(
            _source(company_id=BETA, connection=_connection(ACME))
        )


def test_schema_discovery_refuses_another_companys_connection_before_connecting(
    monkeypatch,
):
    monkeypatch.setattr(schema_discovery.psycopg, "connect", _fail_connect)
    with pytest.raises(ConnectionNotAllowed):
        schema_discovery.discover_postgres_schema(
            _source(company_id=BETA, connection=_connection(ACME))
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"credential_env_var": "JWT_SECRET"},
        {"credential_env_var": "DATABASE_PASSWORD"},
        {"credential_env_var": "ACME_OTHER_PASSWORD"},  # not on the allowlist
        {"host": "postgres"},
        {"host": "REDIS"},
        {"host": "localhost"},
        {"host": "127.0.0.1"},
        {"host": "::1"},
        {"host": "169.254.169.254"},
    ],
)
def test_registering_refuses_platform_secrets_and_internal_hosts(overrides):
    fields = {
        "company_id": ACME,
        "name": "acme-demo",
        "host": "demo_business_acme",
        "port": 5432,
        "database": "acme_business",
        "username": "acme_readonly",
        "schema_name": "public",
        "credential_env_var": "ACME_DEMO_DATABASE_PASSWORD",
        "operator": "test",
    }
    with pytest.raises(ValueError):
        new_connection(**{**fields, **overrides})


def test_registering_builds_an_env_credential_reference():
    connection = new_connection(
        company_id=ACME,
        name="acme-demo",
        host="demo_business_acme",
        port=5432,
        database="acme_business",
        username="acme_readonly",
        schema_name="public",
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        operator="test",
    )

    assert connection.credential_ref == "env:ACME_DEMO_DATABASE_PASSWORD"
    assert connection.company_id == ACME


def test_sql_without_a_company_source_never_falls_back_to_the_default_database(
    monkeypatch,
):
    # The platform's default business database is not a tenant's to reach.
    monkeypatch.setattr(sql_executor.psycopg, "connect", _fail_connect)
    with pytest.raises(ConnectionNotAllowed, match="no company data source"):
        sql_executor._connection_details(None)


def test_sql_tool_reports_a_refused_connection_as_not_repairable(monkeypatch):
    from app.modules.analysis.data import sql_tool
    from app.modules.analysis.tool_protocol import ToolInput

    def refuse(*_args, **_kwargs):
        raise ConnectionNotAllowed("data source points at another company's connection")

    monkeypatch.setattr(sql_tool, "execute_readonly_sql", refuse)

    output = sql_tool.SQLTool().execute(ToolInput(parameters={"sql": "SELECT 1"}))

    assert output.success is False
    assert output.error_code == "data_source_not_allowed"
    assert output.repairable is False
    assert "another company" not in (output.error or "")


def test_template_query_tool_is_not_wired_into_the_main_chain():
    # It reads the platform's default business credentials, so it must stay
    # unreachable until it resolves a company connection (A11b conclusion).
    from pathlib import Path

    app_root = Path(__file__).resolve().parents[3] / "app"
    users = [
        path
        for path in app_root.rglob("*.py")
        if "TemplateQueryTool(" in path.read_text(encoding="utf-8")
        and path.name != "template_query.py"
    ]
    assert users == []
