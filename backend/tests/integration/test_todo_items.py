from fastapi.testclient import TestClient
import pytest
from app.models.company import Company, CompanyMember
from app.models.user import User
from app.core.auth import get_current_user
from app.main import app


@pytest.fixture(autouse=True)
def approved_company_member(db_session, test_user: User) -> Company:
    company = Company(name="todo-test-company")
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


def test_create_todo_item(client: TestClient, test_user: User) -> None:
    create_respense = client.post(
        "/todo-items",
        json={
            "title": "1",
            "description": "guanyu1",
        },
    )
    created = create_respense.json()
    assert create_respense.status_code == 201
    assert created["id"] is not None
    assert created["user_id"] == test_user.id
    assert created["title"] == "1"
    assert created["description"] == "guanyu1"
    assert created["status"] == "todo"
    assert created["priority"] == "medium"
    assert created["due_at"] is None


def test_update_todo_item_status(
    client: TestClient,
) -> None:
    create_respense = client.post(
        "/todo-items",
        json={
            "title": "1",
            "description": "guanyu1",
        },
    )
    created = create_respense.json()
    item_id = created["id"]
    response = client.patch(f"/todo-items/{item_id}", json={"status": "done"})
    assert response.status_code == 200
    update = response.json()
    assert update["status"] == "done"

    get_response = client.get(f"/todo-items/{item_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "done"


def test_user_cannot_update_another_users_todo_item(
    client: TestClient,
    db_session,
    test_user: User,
) -> None:
    response = client.post(
        "/todo-items",
        json={
            "title": "1",
            "description": "guanyu1",
        },
    )
    assert response.status_code == 201
    created = response.json()
    item_id = created["id"]
    other_user = User(name="B", api_key="miyao")
    db_session.add(other_user)
    db_session.flush()
    other_company = Company(name="other-todo-company")
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

    def overrides_return_oyther_user():
        return other_user

    app.dependency_overrides[get_current_user] = overrides_return_oyther_user

    response1 = client.patch(f"/todo-items/{item_id}", json={"status": "done"})

    assert response1.status_code == 404

    def return_a_user():
        return test_user

    app.dependency_overrides[get_current_user] = return_a_user
    a_response = client.get(f"/todo-items/{item_id}")

    assert a_response.status_code == 200
    assert a_response.json()["status"] == "todo"


def test_delete_todo_item(
    client: TestClient,
    db_session,
    test_user: User,
):
    response = client.post(
        "/todo-items",
        json={
            "title": "2",
            "description": "guanyu2",
        },
    )
    assert response.status_code == 201
    reaa = response.json()
    item_id = reaa["id"]
    delete_response = client.delete(f"/todo-items/{item_id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/todo-items/{item_id}")

    assert get_response.status_code == 404


def test_list_todo_items_filters_by_status(
    client: TestClient,
):
    # userA = User(name="A",api_key="A123")
    # db_session.add(userA)
    # db_session.flush()
    # def return_useA():
    #     return userA
    # app.dependency_overrides[get_current_user] = return_useA
    response_A = client.post(
        "/todo-items", json={"title": "A", "description": "A  de "}
    )
    assert response_A.status_code == 201
    item_A_id = response_A.json()["id"]

    response_B = client.post(
        "/todo-items", json={"title": "B", "description": "B  de "}
    )
    assert response_B.status_code == 201
    item_B_id = response_B.json()["id"]

    update = client.patch(f"/todo-items/{item_B_id}", json={"status": "done"})
    assert update.status_code == 200

    get_response = client.get("/todo-items?status=todo")
    assert get_response.status_code == 200
    todo_items = get_response.json()
    assert len(todo_items) == 1
    assert todo_items[0]["id"] == item_A_id
    assert todo_items[0]["title"] == "A"

    getdone_response = client.get("/todo-items?status=done")
    done_items = getdone_response.json()
    assert len(done_items) == 1
    assert done_items[0]["id"] == item_B_id
    assert done_items[0]["status"] == "done"


def test_update_todo_item_rejects_empty_body(client: TestClient):
    created_response = client.post(
        "/todo-items", json={"title": "ceshi", "description": "ceshi 1"}
    )
    assert created_response.status_code == 201
    created = created_response.json()
    item_id = created["id"]
    update = client.patch(f"/todo-items/{item_id}", json={})
    assert update.status_code == 422

    get = client.get(f"/todo-items/{item_id}")
    assert get.status_code == 200
    get_a = get.json()
    assert get_a["status"] == "todo"


def test_create_todo_item_rejects_blank_title(client: TestClient):
    create1 = client.post("/todo-items", json={"title": "   ", "description": "111de"})
    assert create1.status_code == 422
    created = create1.json()
    assert created["code"] == "validation_error"
    assert created["details"][0]["type"] == "string_too_short"
