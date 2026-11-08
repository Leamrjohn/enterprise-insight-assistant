import os
from collections.abc import Generator
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_NAME"] = "agent_platform_test"
os.environ["MIGRATION_DATABASE_USER"] = "agent_migrator"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["LOG_DIR"] = "./.test-logs"
os.environ["STORAGE_DIR"] = "./.test-storage"


import pytest
from alembic import command
from alembic.config import Config
from app.db.session import engine, get_db
from app.main import app
from app.modules.identity.authentication import get_current_user
from app.modules.identity.models import User
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def migrated_test_database() -> None:
    if engine.url.database != "agent_platform_test":
        raise RuntimeError("Tests must run against agent_platform_test")

    alembic_config = Config(BACKEND_DIR / "alembic.ini")
    command.upgrade(alembic_config, "head")


@pytest.fixture
def db_session(
    migrated_test_database: None,
) -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(name="test-user", api_key="test-api-key-for-testing")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def client(
    db_session: Session,
    test_user: User,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_get_current_user() -> User:
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def frozen_upload_client(db_session: Session, test_user: User):
    """Exercise retained module contracts without reopening the production app."""
    from app.api.router import router
    from app.core.middleware import request_context_middleware
    from app.modules.documents.api import upload_router
    from app.modules.input_artifacts.api import router as attachment_router

    isolated_app = FastAPI(exception_handlers=app.exception_handlers)
    isolated_app.middleware("http")(request_context_middleware)
    isolated_app.include_router(router)
    isolated_app.include_router(upload_router)
    isolated_app.include_router(attachment_router)
    isolated_app.dependency_overrides[get_db] = lambda: db_session
    isolated_app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(isolated_app) as test_client:
        yield test_client
