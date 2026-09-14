import pytest
from fastapi.testclient import TestClient
from uuid import uuid4

from app.modules.documents import api as document_api
from app.main import app
from app.modules.organizations.models import Company, CompanyMember
from app.modules.identity.models import User
from app.db.session import get_db


def _add_company_membership(db_session, user: User) -> None:
    company = Company(name="error-test-company")
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


def test_unhandled_exception_returns_safe_500(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
):
    api_key = uuid4().hex
    user = User(name="test-errors", api_key=api_key)
    db_session.add(user)
    db_session.flush()
    _add_company_membership(db_session, user)

    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(
        document_api,
        "get_document_service",
        raise_runtime_error,
    )

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/documents",
                headers={"X-API-Key": api_key},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 500
    assert response.headers.get("X-Request-ID")
    assert response.json() == {
        "code": "internal_error",
        "message": "服务器内部错误，请稍后重试。",
        "details": [],
    }
    assert "sensitive internal detail" not in response.text


def test_unhandled_exception_preserves_incoming_request_id(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
):
    api_key = uuid4().hex
    user = User(name="test-errors", api_key=api_key)
    db_session.add(user)
    db_session.flush()
    _add_company_membership(db_session, user)

    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(
        document_api,
        "get_document_service",
        raise_runtime_error,
    )

    def override_get_db():
        yield db_session

    request_id = "test-request-id"
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/documents",
                headers={"X-API-Key": api_key, "X-Request-ID": request_id},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == request_id
