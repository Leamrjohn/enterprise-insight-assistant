from types import SimpleNamespace
from unittest.mock import Mock

import app.modules.documents.api as document_api
import pytest
from app.core.exceptions import InsufficientStorageError
from fastapi.testclient import TestClient


@pytest.fixture
def client(frozen_upload_client):
    return frozen_upload_client


def test_upload_document_enqueues_ingestion_and_returns_pending(
    client: TestClient,
    monkeypatch,
) -> None:
    pending_document = SimpleNamespace(
        id=123,
        uploaded_by_user_id=1,
        name="report.txt",
        content=None,
        source="upload",
        file_type=".txt",
        file_size=5,
        sha256="test-sha256",
        status="pending",
        created_at=None,
        updated_at=None,
    )
    upload_document = Mock(return_value=pending_document)
    delay = Mock()
    monkeypatch.setattr(
        document_api,
        "upload_document_service",
        upload_document,
    )
    monkeypatch.setattr(document_api.process_document_task, "delay", delay)

    company = client.post("/companies", json={"name": "upload-test-company"})
    assert company.status_code == 201

    response = client.post(
        "/documents/upload",
        files={"file": ("report.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 202
    assert response.json()["id"] == 123
    assert response.json()["status"] == "pending"
    assert response.json()["error_message"] is None
    upload_document.assert_called_once()
    delay.assert_called_once_with(document_id=123, company_id=company.json()["id"])


def test_upload_document_returns_507_when_application_storage_is_full(
    client: TestClient,
    monkeypatch,
) -> None:
    def disk_full(**_kwargs):
        raise InsufficientStorageError("application storage is full")

    monkeypatch.setattr(document_api, "upload_document_service", disk_full)

    company = client.post("/companies", json={"name": "upload-storage-full-company"})
    assert company.status_code == 201

    response = client.post(
        "/documents/upload",
        files={"file": ("report.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 507
    assert response.json()["code"] == "insufficient_storage"
    assert response.json()["message"] == "存储空间不足，请稍后重试。"
