"""Company onboarding and current-company management integration tests."""

from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.main import app
from app.models.company import BusinessDataSource, CompanyMember
from app.models.user import User


def _bootstrap_company(client: TestClient, name: str) -> int:
    response = client.post("/companies", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _create_invitation(client: TestClient) -> str:
    response = client.post("/company/invitations", json={"max_uses": 2})
    assert response.status_code == 201
    return response.json()["code"]


def test_pending_account_needs_approval_before_company_access(
    client: TestClient, test_user: User
) -> None:
    _bootstrap_company(client, "Acme")
    invitation_code = _create_invitation(client)

    registered = client.post(
        "/auth/membership-applications",
        json={
            "name": "new analyst",
            "username": "new-analyst",
            "password": "new-analyst-password",
            "invitation_code": invitation_code,
        },
    )
    assert registered.status_code == 201
    application = registered.json()
    assert application["status"] == "pending"

    # Remove the fixture's active-user shortcut: this request proves the
    # persisted account state, rather than a FastAPI dependency override.
    app.dependency_overrides.pop(get_current_user)
    try:
        login = client.post(
            "/auth/login",
            json={"username": "new-analyst", "password": "new-analyst-password"},
        )
        assert login.status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = lambda: test_user

    approved = client.post(
        f"/company/membership-applications/{application['id']}/approve"
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    app.dependency_overrides.pop(get_current_user)
    try:
        login = client.post(
            "/auth/login",
            json={"username": "new-analyst", "password": "new-analyst-password"},
        )
        assert login.status_code == 200
        company = client.get(
            "/me/company",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert company.status_code == 200
        assert company.json()["role"] == "analyst"
    finally:
        app.dependency_overrides[get_current_user] = lambda: test_user


def test_rejected_account_can_only_reapply_to_the_same_company(
    client: TestClient, test_user: User
) -> None:
    _bootstrap_company(client, "Acme")
    invitation_code = _create_invitation(client)
    registered = client.post(
        "/auth/membership-applications",
        json={
            "name": "reapply analyst",
            "username": "reapply-analyst",
            "password": "reapply-password",
            "invitation_code": invitation_code,
        },
    ).json()

    rejected = client.post(
        f"/company/membership-applications/{registered['id']}/reject"
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    resubmitted = client.post(
        "/auth/membership-applications/reapply",
        json={
            "username": "reapply-analyst",
            "password": "reapply-password",
            "invitation_code": invitation_code,
        },
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["id"] == registered["id"]
    assert resubmitted.json()["status"] == "pending"


def test_non_admin_cannot_create_invitation_or_approve_application(
    client: TestClient, db_session, test_user: User
) -> None:
    company_id = _bootstrap_company(client, "Acme")
    analyst = User(name="analyst", api_key="analyst-api-key")
    db_session.add(analyst)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=company_id,
            user_id=analyst.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()

    app.dependency_overrides[get_current_user] = lambda: analyst
    try:
        invitation = client.post("/company/invitations", json={"max_uses": 1})
        assert invitation.status_code == 403
    finally:
        app.dependency_overrides[get_current_user] = lambda: test_user


def test_admin_member_list_contains_identity_and_cannot_disable_last_owner(
    client: TestClient, db_session, test_user: User
) -> None:
    _bootstrap_company(client, "Acme")
    members = client.get("/company/members")
    assert members.status_code == 200
    owner = members.json()[0]
    assert owner["user_name"] == "test-user"
    assert owner["is_active"] is True

    disabled = client.patch(
        f"/company/members/{owner['id']}", json={"status": "disabled"}
    )
    assert disabled.status_code == 409


def test_analyst_can_choose_a_data_source_without_reading_its_configuration(
    client: TestClient, db_session, test_user: User
) -> None:
    company_id = _bootstrap_company(client, "Acme")
    source = BusinessDataSource(
        company_id=company_id,
        name="经营数据库",
        connection_config={
            "host": "private-db",
            "database": "business",
            "user": "readonly",
        },
        credential_env_var="BUSINESS_DATABASE_PASSWORD",
        status="ready",
    )
    analyst = User(name="analyst", api_key="analyst-source-key")
    db_session.add_all([source, analyst])
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=company_id,
            user_id=analyst.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()

    app.dependency_overrides[get_current_user] = lambda: analyst
    try:
        assert client.get("/company/data-sources").status_code == 403
        choices = client.get("/company/assistant-data-sources")
        assert choices.status_code == 200
        assert choices.json() == [
            {
                "id": source.id,
                "name": "经营数据库",
                "status": "ready",
                "active_schema_snapshot_id": None,
            }
        ]
    finally:
        app.dependency_overrides[get_current_user] = lambda: test_user
