from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_database_fixture_uses_test_database(
    db_session: Session,
) -> None:
    database_name = db_session.execute(text("SELECT current_database()")).scalar_one()

    assert database_name == "agent_platform_test"


def test_health_endpoints(
    client: TestClient,
) -> None:
    live_response = client.get("/health/live")
    ready_response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json() == {
        "status": "ok",
        "database": None,
    }
    assert ready_response.status_code == 200
    assert ready_response.json() == {
        "status": "ok",
        "database": "ok",
    }
    assert live_response.headers["X-Request-ID"]
