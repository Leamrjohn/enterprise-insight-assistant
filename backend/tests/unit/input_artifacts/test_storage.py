from io import BytesIO

import pytest
from app.core.exceptions import (
    EmptyInputArtifactError,
    InputArtifactTooLargeError,
    UnsupportedInputArtifactTypeError,
)
from app.core.settings import get_settings
from app.modules.input_artifacts.storage import (
    inspect_input_artifact_file,
    store_input_artifact_file,
)


def test_inspect_input_artifact_file_returns_metadata_and_rewinds_stream(
    tmp_path,
) -> None:
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})
    payload = b"region,sales\neast,10\n"
    stream = BytesIO(payload)
    stream.read(4)

    inspected = inspect_input_artifact_file(
        file_stream=stream,
        original_filename="C:\\fakepath\\Sales.CSV",
        settings=settings,
    )

    assert inspected.original_filename == "Sales.CSV"
    assert inspected.category == "table"
    assert inspected.byte_size == len(payload)
    assert inspected.sha256 == (
        "1c4b64e728e314881fae92978e7ba65d5d2aec2a1714e326463c14db38bc7a98"
    )
    assert stream.read() == payload
    assert not settings.input_artifact_quarantine_dir.exists()


def test_inspect_input_artifact_file_rewinds_after_filename_rejection(tmp_path) -> None:
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})
    stream = BytesIO(b"not executable")
    stream.read(4)

    with pytest.raises(UnsupportedInputArtifactTypeError):
        inspect_input_artifact_file(
            file_stream=stream,
            original_filename="payload.exe",
            settings=settings,
        )

    assert stream.read() == b"not executable"
    assert not settings.input_artifact_quarantine_dir.exists()


def test_store_input_artifact_file_writes_to_quarantine(tmp_path) -> None:
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    stored = store_input_artifact_file(
        file_stream=BytesIO(b"region,sales\neast,10\n"),
        original_filename="C:\\fakepath\\Sales.CSV",
        settings=settings,
    )

    assert stored.original_filename == "Sales.CSV"
    assert stored.raw_object_key.startswith("input-artifacts/quarantine/")
    assert stored.category == "table"
    assert stored.byte_size == len(b"region,sales\neast,10\n")
    assert (
        stored.sha256
        == "1c4b64e728e314881fae92978e7ba65d5d2aec2a1714e326463c14db38bc7a98"
    )
    assert stored.absolute_path.read_bytes() == b"region,sales\neast,10\n"


def test_store_input_artifact_file_rejects_unsupported_extension(tmp_path) -> None:
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})

    with pytest.raises(UnsupportedInputArtifactTypeError):
        store_input_artifact_file(
            file_stream=BytesIO(b"not executable"),
            original_filename="payload.exe",
            settings=settings,
        )

    assert not settings.input_artifact_quarantine_dir.exists()


def test_store_input_artifact_file_removes_empty_or_oversized_files(tmp_path) -> None:
    settings = get_settings().model_copy(
        update={
            "storage_dir": tmp_path,
            "input_artifact_document_max_size_mb": 1,
        }
    )

    with pytest.raises(EmptyInputArtifactError):
        store_input_artifact_file(
            file_stream=BytesIO(),
            original_filename="empty.txt",
            settings=settings,
        )
    with pytest.raises(InputArtifactTooLargeError):
        store_input_artifact_file(
            file_stream=BytesIO(b"x" * (1024 * 1024 + 1)),
            original_filename="large.txt",
            settings=settings,
        )

    assert list(settings.input_artifact_quarantine_dir.iterdir()) == []
