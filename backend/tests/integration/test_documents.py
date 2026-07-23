from fastapi.testclient import TestClient
import pytest
from app.core.auth import get_current_user
from app.main import app
from app.models.user import User


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

    assert create_response.status_code == 200
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
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "pytest-document-updated"

    delete_response = client.delete(f"/documents/{document_id}")
    assert delete_response.status_code == 200

    missing_response = client.get(f"/documents/{document_id}")
    assert missing_response.status_code == 404
    assert missing_response.headers["X-Request-ID"]
    assert missing_response.json() == {
        "code": "not_found",
        "message": "document not found",
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
    assert create_response.status_code == 200
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
) -> None:
    create_response = client.post(
        "/documents",
        json={"name": "yuequanceshi", "content": "此次为越权测试", "source": "ceshi"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    document_id = created["id"]
    other_user = User(name="ceshiyuequan", api_key="123456")
    db_session.add(other_user)
    db_session.flush()

    def return_other_user():
        return other_user

    app.dependency_overrides[get_current_user] = return_other_user
    get_response = client.get(f"/documents/{document_id}")
    assert get_response.status_code == 404
