from fastapi.testclient import TestClient
from uuid import uuid4
from app.models.user import User
from app.db.session import get_db
from app.main import app


def test_get_current_user(db_session):
    api_key = uuid4().hex
    user = User(name = "123",api_key =api_key )
    db_session.add(user)
    db_session.flush()

    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            test1_response = client.get("/auth/me",headers= {"X-API-Key":user.api_key})

            assert test1_response.status_code == 200
            assert test1_response.json()["name"] == "123"

            test2_response = client.get("/auth/me")
            assert test2_response.status_code == 401

            test3_response = client.get("/auth/me",headers= {"X-API-Key":"invalid-key"})
            assert test3_response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db,None)
