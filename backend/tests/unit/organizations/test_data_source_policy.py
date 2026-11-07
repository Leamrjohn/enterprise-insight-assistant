import pytest
from app.modules.analysis.data import sql_executor
from app.modules.organizations.models import BusinessDataSource
from app.modules.organizations.schemas import BusinessDataSourceCreate
from pydantic import ValidationError

DEMO_CONNECTION = {
    "host": "demo_business_acme",
    "port": 5432,
    "database": "acme_business",
    "user": "acme_readonly",
    "schema": "public",
}


def _source(credential_env_var: str, host: str = "demo_business_acme"):
    return BusinessDataSource(
        company_id=1,
        name="tenant-db",
        dialect="postgresql",
        connection_config={**DEMO_CONNECTION, "host": host},
        credential_env_var=credential_env_var,
    )


@pytest.mark.parametrize(
    "name", ["JWT_SECRET", "DATABASE_PASSWORD", "ACME_OTHER_PASSWORD"]
)
def test_create_rejects_credential_outside_allowlist(name):
    with pytest.raises(ValidationError):
        BusinessDataSourceCreate(
            name="tenant-db", connection=DEMO_CONNECTION, credential_env_var=name
        )


@pytest.mark.parametrize(
    "host", ["postgres", "REDIS", "localhost", "127.0.0.1", "::1", "169.254.169.254"]
)
def test_create_rejects_platform_internal_host(host):
    with pytest.raises(ValidationError):
        BusinessDataSourceCreate(
            name="tenant-db",
            connection={**DEMO_CONNECTION, "host": host},
            credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        )


def test_create_accepts_demo_source():
    request = BusinessDataSourceCreate(
        name="tenant-db",
        connection=DEMO_CONNECTION,
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
    )
    assert request.credential_env_var == "ACME_DEMO_DATABASE_PASSWORD"


def test_query_time_rejects_stored_platform_secret_before_reading_it(monkeypatch):
    # A row saved before this check existed must not be able to borrow the JWT key.
    monkeypatch.setenv("JWT_SECRET", "platform-signing-key")
    with pytest.raises(ValueError) as raised:
        sql_executor._connection_details(_source("JWT_SECRET"))
    assert "platform-signing-key" not in str(raised.value)


def test_query_time_rejects_stored_internal_host(monkeypatch):
    monkeypatch.setenv("ACME_DEMO_DATABASE_PASSWORD", "demo")
    with pytest.raises(ValueError):
        sql_executor._connection_details(
            _source("ACME_DEMO_DATABASE_PASSWORD", "postgres")
        )


def test_query_time_keeps_demo_source(monkeypatch):
    monkeypatch.setenv("ACME_DEMO_DATABASE_PASSWORD", "demo")
    details = sql_executor._connection_details(_source("ACME_DEMO_DATABASE_PASSWORD"))
    assert details["host"] == "demo_business_acme"
    assert details["password"] == "demo"


def test_schema_discovery_rejects_platform_secret_without_connecting(monkeypatch):
    from app.modules.analysis.catalog import schema_discovery

    def fail_connect(**_kwargs):
        raise AssertionError("must not connect")

    monkeypatch.setenv("JWT_SECRET", "platform-signing-key")
    monkeypatch.setattr(schema_discovery.psycopg, "connect", fail_connect)
    with pytest.raises(ValueError):
        schema_discovery.discover_postgres_schema(_source("JWT_SECRET"))


def test_platform_secret_stays_refused_even_if_allowlisted():
    from app.modules.organizations.data_source_policy import (
        credential_rejection,
        platform_setting_names,
    )

    reason = credential_rejection(
        "JWT_SECRET",
        allowlist=["jwt_secret", "ACME_DEMO_DATABASE_PASSWORD"],
        platform_names=platform_setting_names(),
    )
    assert reason == "credential is a platform setting"
