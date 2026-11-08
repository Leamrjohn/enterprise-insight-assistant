"""The production app must not expose the frozen upload implementation."""

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "path",
    [
        "/documents/upload",
        "/conversations/1/attachments",
        "/conversations/1/attachment-upload-sessions",
        "/conversations/1/attachment-upload-sessions/example/complete",
    ],
)
def test_upload_writes_are_not_mounted(path):
    # No lifespan: a rejected, unmounted request must not need a database.
    response = TestClient(app).post(path, content=b"not a valid upload")
    assert response.status_code in {404, 405}


def test_openapi_excludes_uploads_but_keeps_json_documents():
    paths = app.openapi()["paths"]
    assert "post" in paths["/documents"]
    assert "/documents/upload" not in paths
    assert not any(
        "attachments" in path or "attachment-upload" in path for path in paths
    )
