from uuid import uuid4

from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.modules.identity.models import User
from app.modules.organizations.models import Company, CompanyMember
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def test_get_current_user(db_session):
    api_key = uuid4().hex
    user = User(name="123", api_key=api_key)
    db_session.add(user)
    db_session.flush()
    company = Company(name="auth-test-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            test1_response = client.get("/auth/me", headers={"X-API-Key": user.api_key})

            assert test1_response.status_code == 200
            assert test1_response.json()["name"] == "123"
            assert test1_response.json()["company_name"] == "auth-test-company"
            assert test1_response.json()["role"] == "analyst"

            test2_response = client.get("/auth/me")
            assert test2_response.status_code == 401

            test3_response = client.get(
                "/auth/me", headers={"X-API-Key": "invalid-key"}
            )
            assert test3_response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_password_login_and_jwt_can_read_current_user(db_session) -> None:
    user = User(
        name="登录用户",
        username="login-user",
        password_hash=hash_password("correct-password"),
        api_key="legacy-login-test-key",
    )
    db_session.add(user)
    db_session.flush()
    company = Company(name="login-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            rejected = client.post(
                "/auth/login",
                json={"username": "login-user", "password": "wrong-password"},
            )
            assert rejected.status_code == 401

            login = client.post(
                "/auth/login",
                json={"username": "login-user", "password": "correct-password"},
            )
            assert login.status_code == 200
            token = login.json()["access_token"]

            me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["username"] == "login-user"
            assert me.json()["company_name"] == "login-company"

            changed = client.post(
                "/auth/me/password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "current_password": "correct-password",
                    "new_password": "changed-password",
                },
            )
            assert changed.status_code == 204
            assert (
                client.get(
                    "/auth/me", headers={"Authorization": f"Bearer {token}"}
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/auth/login",
                    json={"username": "login-user", "password": "correct-password"},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/auth/login",
                    json={"username": "login-user", "password": "changed-password"},
                ).status_code
                == 200
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_bootstrap_owner_only_works_before_any_company() -> None:
    # Bootstrap only owns these three tables; a dedicated in-memory database
    # avoids coupling its zero-company precondition to shared PostgreSQL data.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for table in (User.__table__, Company.__table__, CompanyMember.__table__):
        table.create(engine)
    suffix = uuid4().hex

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/auth/bootstrap-owner",
                json={
                    "name": "初始管理员",
                    "company_name": "Acme",
                    "username": f"owner-{suffix}",
                    "password": "owner-password",
                },
            )
            assert created.status_code == 201
            with Session(engine) as db:
                assert db.query(CompanyMember).one().role == "owner"

            repeated = client.post(
                "/auth/bootstrap-owner",
                json={
                    "name": "第二位管理员",
                    "company_name": "Other",
                    "username": f"owner-2-{suffix}",
                    "password": "owner-password",
                },
            )
            assert repeated.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_legacy_api_key_can_set_an_initial_password_once(db_session) -> None:
    user = User(name="旧账户", api_key="legacy-password-setup-key")
    db_session.add(user)
    db_session.flush()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/auth/initial-password",
                headers={"X-API-Key": "legacy-password-setup-key"},
                json={"username": "legacy-user", "password": "legacy-password"},
            )
            assert response.status_code == 204
            assert (
                client.post(
                    "/auth/login",
                    json={"username": "legacy-user", "password": "legacy-password"},
                ).status_code
                == 200
            )
            assert (
                client.post(
                    "/auth/initial-password",
                    headers={"X-API-Key": "legacy-password-setup-key"},
                    json={"username": "other", "password": "other-password"},
                ).status_code
                == 409
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
