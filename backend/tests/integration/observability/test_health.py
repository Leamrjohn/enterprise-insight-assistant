from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def test_database_fixture_uses_test_database(
    db_session: Session,
) -> None:
    database_name = db_session.execute(text("SELECT current_database()")).scalar_one()

    assert database_name == "agent_platform_test"


def test_health_endpoints(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_redis", lambda: True
    )
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_object_storage", lambda: "ok"
    )
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_task_capacity", lambda: "ok"
    )
    live_response = client.get("/health/live")
    ready_response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json() == {
        "status": "ok",
        "database": None,
        "redis": None,
        "object_storage": None,
        "task_capacity": None,
    }
    assert ready_response.status_code == 200
    assert ready_response.json() == {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
        "object_storage": "ok",
        "task_capacity": "ok",
    }
    assert live_response.headers["X-Request-ID"]


def test_readiness_reports_redis_unavailable(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_redis", lambda: False
    )
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_object_storage", lambda: "ok"
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "ok",
        "redis": "unavailable",
        "object_storage": "unknown",
        "task_capacity": "unknown",
    }


def test_readiness_reports_object_storage_unavailable(
    monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_redis", lambda: True
    )
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_object_storage",
        lambda: "unavailable",
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "ok",
        "redis": "ok",
        "object_storage": "unavailable",
        "task_capacity": "unknown",
    }


def test_readiness_reports_task_capacity_unavailable(
    monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_redis", lambda: True
    )
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_object_storage", lambda: "ok"
    )
    monkeypatch.setattr(
        "app.modules.observability.health_service.check_task_capacity",
        lambda: "unavailable",
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "ok",
        "redis": "ok",
        "object_storage": "ok",
        "task_capacity": "unavailable",
    }
