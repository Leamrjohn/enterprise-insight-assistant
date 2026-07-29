import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import document as document_api
from app.models.user import User
from app.models.company import Company, CompanyMember
from uuid import uuid4
from app.db.session import get_db


def test_unhandled_error_returns_safe_response(
    monkeypatch: pytest.MonkeyPatch, db_session
):
    api_key = uuid4().hex
    user = User(name="test", api_key=api_key)
    db_session.add(user)
    db_session.flush()
    company = Company(name="document-error-company")
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

    def raise_error(*args, **kwargs):
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(
        document_api,
        "update_document_service",
        raise_error,
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.put(
                "/documents/2",
                json={"name": "xx", "content": "123", "source": "11"},
                headers={"X-API-Key": api_key},
            )

        assert response.status_code == 500
        assert response.headers.get("X-Request-ID")
        assert response.json() == {
            "code": "internal_error",
            "message": "服务器内部错误，请稍后重试。",
            "details": [],
        }
        assert "sensitive internal detail" not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)
