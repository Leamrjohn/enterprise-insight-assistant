from app.core.auth import get_current_user
from app.main import app
from app.models.company import Company, CompanyMember
from app.models.user import User
from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def approved_company_member(db_session, test_user: User) -> Company:
    company = Company(name="prompt-template-test-company")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=company.id,
            user_id=test_user.id,
            role="owner",
            status="approved",
        )
    )
    db_session.flush()
    return company


def test_prompt_template_1(client: TestClient, test_user: User):
    created_response = client.post(
        "/prompt-templates",
        json={
            "name": "ceshi",
            "template": "ceshineirong",
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["name"] == "ceshi"
    assert created["template"] == "ceshineirong"
    assert created["description"] is None
    id = created["id"]

    get_response = client.get(f"/prompt-templates/{id}")
    assert get_response.status_code == 200
    geted = get_response.json()
    assert geted["name"] == "ceshi"
    assert geted["template"] == "ceshineirong"

    created1_response = client.post(
        "/prompt-templates",
        json={"name": "ceshi2", "template": "ceshineirong2", "description": "1"},
    )
    assert created1_response.status_code == 201
    get_list_response = client.get("/prompt-templates")
    assert get_list_response.status_code == 200
    get_list = get_list_response.json()

    assert {item["name"] for item in get_list} == {"ceshi", "ceshi2"}
    assert {item["template"] for item in get_list} == {"ceshineirong", "ceshineirong2"}
    assert {item["description"] for item in get_list} == {None, "1"}


def test_prompt_template2(client: TestClient, test_user: User):
    created_response = client.post(
        "/prompt-templates",
        json={
            "name": "ceshi",
            "template": "ceshineirong",
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["name"] == "ceshi"
    assert created["template"] == "ceshineirong"
    assert created["description"] is None
    id = created["id"]

    update_response = client.patch(f"/prompt-templates/{id}", json={"name": "ceshi2"})
    assert update_response.status_code == 200
    updates = update_response.json()
    assert updates["name"] == "ceshi2"

    update_response = client.patch(f"/prompt-templates/{id}", json={})
    assert update_response.status_code == 422


def test_prompt_template22(client: TestClient, test_user: User):
    created_response = client.post(
        "/prompt-templates",
        json={
            "name": "ceshi",
            "template": "ceshineirong",
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["name"] == "ceshi"
    assert created["template"] == "ceshineirong"
    assert created["description"] is None

    created1_response = client.post(
        "/prompt-templates",
        json={
            "name": "ceshi",
            "template": "ceshineirong",
        },
    )
    assert created1_response.status_code == 409


def test_prompt_template3(client: TestClient, test_user: User):
    created_response = client.post(
        "/prompt-templates",
        json={
            "name": "ceshi",
            "template": "ceshineirong",
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    id = created["id"]

    delete_response = client.delete(f"/prompt-templates/{id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/prompt-templates/{id}")
    assert get_response.status_code == 404


def test_prompt_template4(client: TestClient, test_user: User, db_session):
    created_response = client.post(
        "/prompt-templates",
        json={
            "name": "ceshi",
            "template": "ceshineirong",
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    id = created["id"]

    usera = User(name="1", api_key="123")
    db_session.add(usera)
    db_session.flush()
    other_company = Company(name="other-prompt-template-company")
    db_session.add(other_company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=other_company.id,
            user_id=usera.id,
            role="owner",
            status="approved",
        )
    )
    db_session.flush()

    def return_usera():
        return usera

    app.dependency_overrides[get_current_user] = return_usera

    a_get = client.get(f"/prompt-templates/{id}")
    assert a_get.status_code == 404

    a_update = client.patch(
        f"/prompt-templates/{id}", json={"name": "other-user-change"}
    )
    assert a_update.status_code == 404

    a_delete = client.delete(f"/prompt-templates/{id}")
    assert a_delete.status_code == 404

    def return_user():
        return test_user

    app.dependency_overrides[get_current_user] = return_user

    get_response = client.get(f"/prompt-templates/{id}")
    assert get_response.status_code == 200
    getted = get_response.json()

    assert getted["name"] == "ceshi"
    assert getted["template"] == "ceshineirong"
    assert getted["description"] is None
