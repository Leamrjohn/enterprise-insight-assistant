from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.core.auth import get_current_user

from app.models.company import Company, CompanyMember
from app.models.user import User


@pytest.fixture(autouse=True)
def approved_company_member(db_session, test_user: User) -> Company:
    company = Company(name="label-test-company")
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


def test_create_label(client: TestClient, db_session, test_user: User):
    created_response = client.post(
        "/labels", json={"name": "ceshi1", "color": "#3B82F3"}
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["user_id"] == test_user.id
    assert created["name"] == "ceshi1"
    assert created["color"] == "#3B82F3"

    label_id = created["id"]

    get_response = client.get(f"/labels/{label_id}")
    assert get_response.status_code == 200
    geted = get_response.json()
    assert geted["name"] == "ceshi1"

    created2_response = client.post(
        "/labels", json={"name": "ceshi2", "color": "#3B8223"}
    )
    assert created2_response.status_code == 201
    label2_id = created2_response.json()["id"]

    list_response = client.get("/labels")
    assert list_response.status_code == 200
    list = list_response.json()

    assert {item["name"] for item in list} == {"ceshi1", "ceshi2"}
    assert {item["color"] for item in list} == {"#3B82F3", "#3B8223"}

    update_response = client.patch(f"/labels/{label_id}", json={"name": "xiugai ceshi"})
    assert update_response.status_code == 200

    get1_response = client.get(f"/labels/{label_id}")

    assert get1_response.status_code == 200
    get1 = get1_response.json()

    assert get1["name"] == "xiugai ceshi"

    created1_response = client.post(
        "/labels",
        json={
            "name": "ceshi2",
            "color": "#3B8223",
        },
    )
    assert created1_response.status_code == 409

    created2_response = client.post(
        "/labels",
        json={
            "name": "ceshi201",
        },
    )
    assert created2_response.status_code == 201
    assert created2_response.json()["color"] == "#3B82F6"

    update = client.patch(f"/labels/{label_id}", json={})
    assert update.status_code == 422

    created2_response = client.post(
        "/labels",
        json={
            "name": "yanseceshi",
            "color": "red",
        },
    )
    assert created2_response.status_code == 422

    delete_response = client.delete(f"/labels/{label_id}")
    assert delete_response.status_code == 204
    get3_response = client.get(f"/labels/{label_id}")
    assert get3_response.status_code == 404

    other_user = User(name="other-user", api_key="other-api-key")
    db_session.add(other_user)
    db_session.flush()
    other_company = Company(name="other-label-company")
    db_session.add(other_company)
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=other_company.id,
            user_id=other_user.id,
            role="owner",
            status="approved",
        )
    )
    db_session.flush()

    def override_current_user() -> User:
        return other_user

    app.dependency_overrides[get_current_user] = override_current_user

    other_get = client.get(f"/labels/{label2_id}")
    assert other_get.status_code == 404

    other_update = client.patch(f"/labels/{label2_id}", json={"name": "qitayonghu"})
    assert other_update.status_code == 404

    other_delete = client.delete(f"/labels/{label2_id}")
    assert other_delete.status_code == 404

    def return_a_user():
        return test_user

    app.dependency_overrides[get_current_user] = return_a_user

    owner_get = client.get(f"/labels/{label2_id}")
    assert owner_get.status_code == 200
    assert owner_get.json()["name"] == "ceshi2"
