"""A11b: company admins pick a platform-registered connection of their own company."""

import pytest
from app.main import app
from app.modules.analysis.catalog import schema_discovery
from app.modules.identity.authentication import get_current_user
from app.modules.identity.models import User
from app.modules.organizations.connections import ConnectionNotAllowed, new_connection
from app.modules.organizations.models import (
    BusinessDataSource,
    Company,
    CompanyMember,
)
from app.modules.organizations.service import discover_data_source_schema
from fastapi.testclient import TestClient
from sqlalchemy import select


def _register(db_session, company_id: int, name: str):
    connection = new_connection(
        company_id=company_id,
        name=name,
        host="demo_business_acme",
        port=5432,
        database="acme_business",
        username="acme_readonly",
        schema_name="public",
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        operator="test",
    )
    db_session.add(connection)
    db_session.flush()
    return connection


@pytest.fixture
def two_companies(client: TestClient, db_session, test_user: User):
    """Acme (owned by test_user) and Beta (owned by another user), one connection each."""
    response = client.post("/companies", json={"name": "Acme"})
    assert response.status_code == 201
    acme_id = response.json()["id"]
    beta = Company(name="Beta")
    beta_owner = User(name="beta-owner", api_key="beta-owner-key")
    db_session.add_all([beta, beta_owner])
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=beta.id, user_id=beta_owner.id, role="owner", status="approved"
        )
    )
    db_session.flush()
    return {
        "acme_id": acme_id,
        "beta_id": beta.id,
        "beta_owner": beta_owner,
        "acme_connection": _register(db_session, acme_id, "acme-demo"),
        "beta_connection": _register(db_session, beta.id, "beta-demo"),
    }


def _as(user: User):
    app.dependency_overrides[get_current_user] = lambda: user


def test_admin_creates_a_source_from_its_own_connection(client, two_companies):
    connection = two_companies["acme_connection"]

    response = client.post(
        "/company/data-sources",
        json={"name": "经营数据库", "connection_id": connection.id},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["connection_id"] == connection.id
    assert body["connection_name"] == "acme-demo"
    # The platform's address and credential name are not the tenant's to read.
    assert "demo_business_acme" not in str(body)
    assert "ACME_DEMO_DATABASE_PASSWORD" not in str(body)


def test_another_companys_connection_is_refused_at_creation(
    client, db_session, two_companies, test_user
):
    _as(two_companies["beta_owner"])
    try:
        response = client.post(
            "/company/data-sources",
            json={"name": "偷用", "connection_id": two_companies["acme_connection"].id},
        )
    finally:
        _as(test_user)

    assert response.status_code == 404
    rows = db_session.scalars(
        select(BusinessDataSource).where(
            BusinessDataSource.company_id == two_companies["beta_id"]
        )
    ).all()
    assert rows == []


def test_a_tenant_supplied_address_is_no_longer_accepted(client, two_companies):
    response = client.post(
        "/company/data-sources",
        json={
            "name": "自填地址",
            "connection": {
                "host": "demo_business_acme",
                "database": "acme_business",
                "user": "acme_readonly",
            },
            "credential_env_var": "ACME_DEMO_DATABASE_PASSWORD",
        },
    )

    assert response.status_code == 422


def test_connections_list_only_the_current_company(client, two_companies):
    response = client.get("/company/data-connections")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": two_companies["acme_connection"].id,
            "name": "acme-demo",
            "status": "active",
        }
    ]


def test_discovery_refuses_another_companys_connection_before_connecting(
    db_session, two_companies, monkeypatch
):
    # A row bound across companies (only possible by tampering) never connects.
    def fail_connect(**_kwargs):
        raise AssertionError("must not connect")

    monkeypatch.setattr(schema_discovery.psycopg, "connect", fail_connect)
    source = BusinessDataSource(
        company_id=two_companies["beta_id"],
        name="tampered",
        connection_config={},
        credential_env_var="ACME_DEMO_DATABASE_PASSWORD",
        connection=two_companies["acme_connection"],
    )
    db_session.add(source)
    db_session.flush()

    with pytest.raises(RuntimeError) as refused:
        discover_data_source_schema(
            db_session,
            data_source_id=source.id,
            company_id=two_companies["beta_id"],
            user_id=two_companies["beta_owner"].id,
        )

    assert isinstance(refused.value.__cause__, ConnectionNotAllowed)
