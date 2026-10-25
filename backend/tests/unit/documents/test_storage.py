import errno
from io import BytesIO
from pathlib import Path

import pytest
from app.core.exceptions import InsufficientStorageError
from app.core.settings import get_settings
from app.modules.documents.storage import save_document_file


class _DiskFullTarget:
    def __init__(self, target) -> None:
        self._target = target

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self._target.close()

    def write(self, content: bytes) -> int:
        self._target.write(content[:1])
        raise OSError(errno.ENOSPC, "No space left on device")


def test_document_storage_maps_disk_full_and_removes_partial_file(
    tmp_path, monkeypatch
) -> None:
    settings = get_settings().model_copy(update={"storage_dir": tmp_path})
    original_open = Path.open

    def disk_full_open(path, mode="r", *args, **kwargs):
        target = original_open(path, mode, *args, **kwargs)
        if mode == "xb":
            return _DiskFullTarget(target)
        return target

    monkeypatch.setattr(Path, "open", disk_full_open)

    with pytest.raises(InsufficientStorageError, match="storage is full"):
        save_document_file(BytesIO(b"partial document"), "report.txt", settings)

    assert list(settings.upload_dir.iterdir()) == []
