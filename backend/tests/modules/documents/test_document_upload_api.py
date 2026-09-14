from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

import app.modules.documents.api as document_api


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
