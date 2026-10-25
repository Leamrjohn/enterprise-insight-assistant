import pytest
from app.main import app
from app.modules.documents import api as document_api
from app.modules.identity.authentication import get_current_user
from app.modules.identity.models import User
from app.modules.organizations.models import Company, CompanyMember
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def approved_company_for_document_api(db_session, test_user):
    company = Company(name="document-api-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=company.id,
            user_id=test_user.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()
    return company


@pytest.fixture(autouse=True)
def stub_document_dispatch(monkeypatch):
    monkeypatch.setattr(
        document_api.process_document_task,
        "delay",
        lambda **_: None,
    )


def test_document_lifecycle(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/documents",
        json={
            "name": "pytest-document",
            "content": "Stored in the PostgreSQL test database.",
            "source": "pytest",
        },
    )

    assert create_response.status_code == 202
    created = create_response.json()
    document_id = created["id"]

    get_response = client.get(f"/documents/{document_id}")
    assert get_response.status_code == 200
    assert get_response.json() == created

    update_response = client.put(
        f"/documents/{document_id}",
        json={
            "name": "pytest-document-updated",
            "content": "Updated through the real repository.",
            "source": "pytest",
        },
    )
    assert update_response.status_code == 202
    assert update_response.json()["name"] == "pytest-document-updated"

    delete_response = client.delete(f"/documents/{document_id}")
    assert delete_response.status_code == 200

    missing_response = client.get(f"/documents/{document_id}")
    assert missing_response.status_code == 404
    assert missing_response.headers["X-Request-ID"]
    assert missing_response.json() == {
        "code": "not_found",
        "message": "未找到文档。",
        "details": [],
    }


def test_create_document_rejects_missing_content(client: TestClient) -> None:
    response = client.post(
        "/documents",
        json={
            "name": "pytest-document",
            "source": "pytest",
        },
    )
    assert response.status_code == 422
    assert response.headers["X-Request-ID"]

    assert response.json()["code"] == "validation_error"

    assert response.json()["details"][0]["type"] == "missing"
    assert response.json()["details"][0]["loc"] == ["body", "content"]


@pytest.mark.parametrize("content", ["", "   "])
def test_create_document_rejects_blank_content(
    client: TestClient, content: str
) -> None:
    response = client.post(
        "/documents",
        json={
            "name": "pytest-document",
            "content": content,
            "source": "pytest",
        },
    )
    assert response.status_code == 422
    assert response.headers["X-Request-ID"]

    assert response.json()["code"] == "validation_error"

    assert response.json()["details"][0]["type"] == "string_too_short"
    assert response.json()["details"][0]["loc"] == ["body", "content"]


@pytest.mark.parametrize("content", ["", "   "])
def test_update_document_rejects_blank_content(
    client: TestClient, content: str
) -> None:
    create_response = client.post(
        "/documents",
        json={
            "name": "pytest-document",
            "content": "Stored in the PostgreSQL test database.",
            "source": "pytest",
        },
    )
    assert create_response.status_code == 202
    created = create_response.json()
    document_id = created["id"]

    update_response = client.put(
        f"/documents/{document_id}",
        json={
            "name": "pytest-document-updated",
            "content": content,
            "source": "pytest",
        },
    )

    assert update_response.status_code == 422
    assert update_response.headers["X-Request-ID"]

    assert update_response.json()["code"] == "validation_error"
    assert update_response.json()["details"][0]["type"] == "string_too_short"
    assert update_response.json()["details"][0]["loc"] == ["body", "content"]

    get_response = client.get(f"/documents/{document_id}")
    assert get_response.status_code == 200
    assert get_response.json()["content"] == created["content"]


def test_user_cannot_access_another_users_document(
    db_session,
    client: TestClient,
    approved_company_for_document_api,
) -> None:
    create_response = client.post(
        "/documents",
        json={"name": "yuequanceshi", "content": "此次为越权测试", "source": "ceshi"},
    )
    assert create_response.status_code == 202
    created = create_response.json()
    document_id = created["id"]
    other_user = User(name="ceshiyuequan", api_key="123456")
    db_session.add(other_user)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=approved_company_for_document_api.id,
            user_id=other_user.id,
            role="analyst",
            status="approved",
        )
    )
    db_session.flush()

    def return_other_user():
        return other_user

    app.dependency_overrides[get_current_user] = return_other_user
    get_response = client.get(f"/documents/{document_id}")
    # 文档可见性由同公司角色控制；上传者仅承担审计责任，不是授权过滤条件。
    assert get_response.status_code == 200

    update_response = client.put(
        f"/documents/{document_id}",
        json={
            "name": "forbidden-update",
            "content": "other analyst must not change this document",
            "source": "pytest",
        },
    )
    delete_response = client.delete(f"/documents/{document_id}")

    assert update_response.status_code == 404
    assert delete_response.status_code == 404


def test_viewer_cannot_create_document(
    db_session,
    client: TestClient,
    approved_company_for_document_api,
) -> None:
    viewer = User(name="document-viewer", api_key="viewer-key")
    db_session.add(viewer)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=approved_company_for_document_api.id,
            user_id=viewer.id,
            role="viewer",
            status="approved",
        )
    )
    db_session.flush()

    app.dependency_overrides[get_current_user] = lambda: viewer
    response = client.post(
        "/documents",
        json={"name": "forbidden", "content": "not allowed", "source": "pytest"},
    )

    assert response.status_code == 403


def test_analyst_cannot_create_owner_only_document(client: TestClient) -> None:
    response = client.post(
        "/documents",
        json={
            "name": "owner-only",
            "content": "not allowed",
            "source": "pytest",
            "min_view_role": "owner",
        },
    )

    assert response.status_code == 403
