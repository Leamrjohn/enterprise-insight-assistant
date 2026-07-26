from fastapi.testclient import TestClient


def test_upload_text_file(client: TestClient) -> None:
    content = b"hello world, this is a test file."
    response = client.post(
        "/documents/upload",
        files={"file": ("test.txt", content, "text/plain")},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["name"] == "test.txt"
    assert data["file_type"] == ".txt"
    assert data["source"] == "upload"
    assert data["status"] == "pending"
    assert data["sha256"] is not None
    assert data["file_size"] == len(content)


def test_upload_unsupported_file_type(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("test.exe", b"blah", "application/x-msdownload")},
    )
    assert response.status_code == 422


def test_upload_duplicate_file(client: TestClient) -> None:
    content = b"deduplicate me"
    # 第一次上传
    response = client.post(
        "/documents/upload",
        files={"file": ("first.txt", content, "text/plain")},
    )
    assert response.status_code == 202

    # 第二次上传相同内容
    response = client.post(
        "/documents/upload",
        files={"file": ("second.txt", content, "text/plain")},
    )
    assert response.status_code == 409


def test_upload_empty_file(client: TestClient) -> None:
    response = client.post(
        "/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 422
