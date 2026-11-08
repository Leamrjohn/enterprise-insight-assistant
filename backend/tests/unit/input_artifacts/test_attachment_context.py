import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from app.db.session import set_tenant_scope
from app.modules.input_artifacts.attachment_context import (
    AttachmentContextError,
    AttachmentContextLimits,
    build_task_attachment_context,
)
from app.modules.input_artifacts.models import (
    ArtifactParseResult,
    ArtifactProcessingAttempt,
)
from app.modules.input_artifacts.processing.processing_storage import (
    StoredProcessingObject,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.models import Company, CompanyMember
from app.modules.workflow.repository import create_task
from sqlalchemy.orm import Session


class FakeParsedStorage:
    provider_name = "fake"

    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def download_parsed_object(self, *, object_key: str, destination_path: Path):
        content = self.objects[object_key]
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(content)
        return StoredProcessingObject(
            object_key=object_key,
            byte_size=len(content),
            sha256_hex=hashlib.sha256(content).hexdigest(),
        )


def _create_ready_parse_result(
    db: Session,
    *,
    user_id: int,
    company_id: int,
    suffix: str,
    text: str,
    trust_level: str = "untrusted",
):
    version = create_received_input_artifact_version(
        db,
        company_id=company_id,
        uploaded_by_user_id=user_id,
        kind="attachment",
        original_filename=f"attachment-{suffix}.txt",
        raw_object_key=f"input-artifacts/quarantine/{company_id}/{suffix}",
        byte_size=1,
        sha256=(suffix * 64)[:64],
        commit=False,
    )
    manifest_key = f"input-artifacts/parsed/{version.id}/manifest.json"
    text_key = f"input-artifacts/parsed/{version.id}/extracted.txt"
    manifest = json.dumps(
        {"content_trust_level": trust_level, "source_format": "txt"},
        ensure_ascii=False,
    ).encode()
    text_bytes = text.encode()
    attempt = ArtifactProcessingAttempt(
        artifact_version_id=version.id,
        stage="parse",
        attempt_number=1,
        status="succeeded",
        processor_name="test-parser",
        processor_version="1.0",
        trace_id=f"attachment-context-{suffix}",
        finished_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.flush()
    parse_result = ArtifactParseResult(
        artifact_version_id=version.id,
        processing_attempt_id=attempt.id,
        result_schema_version="1.0",
        manifest_object_key=manifest_key,
        manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        extracted_text_object_key=text_key,
        extracted_text_sha256=hashlib.sha256(text_bytes).hexdigest(),
        extracted_text_char_count=len(text),
    )
    db.add(parse_result)
    db.flush()
    version.status = "ready"
    version.active_parse_result_id = parse_result.id
    db.flush()
    return version, {manifest_key: manifest, text_key: text_bytes}


def _company_scope(db: Session, user_id: int) -> Company:
    company = Company(name="attachment-context")
    db.add(company)
    db.flush()
    db.add(
        CompanyMember(
            company_id=company.id, user_id=user_id, role="analyst", status="approved"
        )
    )
    db.flush()
    set_tenant_scope(db, company.id)
    return company


def test_task_attachment_context_is_ordered_bounded_and_not_raw_in_manifest(
    db_session: Session, test_user
) -> None:
    company = _company_scope(db_session, test_user.id)
    first, first_objects = _create_ready_parse_result(
        db_session,
        user_id=test_user.id,
        company_id=company.id,
        suffix="a",
        text="abcdef",
    )
    second, second_objects = _create_ready_parse_result(
        db_session,
        user_id=test_user.id,
        company_id=company.id,
        suffix="b",
        text="uvwxyz",
    )
    task = create_task(
        db_session,
        user_id=test_user.id,
        question="分析附件",
        company_id=company.id,
        input_artifact_version_ids=[second.id, first.id],
    )
    result = build_task_attachment_context(
        db_session,
        task_id=task.id,
        company_id=company.id,
        storage=FakeParsedStorage(first_objects | second_objects),
        limits=AttachmentContextLimits(max_chars_per_attachment=4, max_total_chars=6),
    )

    assert [item["artifact_version_id"] for item in result.planner_payload] == [
        second.id,
        first.id,
    ]
    assert [item["extracted_text"] for item in result.planner_payload] == ["uvwx", "ab"]
    assert result.selection_manifest["selected_char_count"] == 6
    assert "uvwxyz" not in json.dumps(result.selection_manifest)
    assert result.selection_manifest["items"][1]["truncated"] is True


def test_task_attachment_context_fails_closed_when_manifest_lacks_trust_marker(
    db_session: Session, test_user
) -> None:
    company = _company_scope(db_session, test_user.id)
    version, objects = _create_ready_parse_result(
        db_session,
        user_id=test_user.id,
        company_id=company.id,
        suffix="c",
        text="hello",
        trust_level="trusted",
    )
    task = create_task(
        db_session,
        user_id=test_user.id,
        question="分析附件",
        company_id=company.id,
        input_artifact_version_ids=[version.id],
    )

    with pytest.raises(AttachmentContextError, match="untrusted_contract_missing"):
        build_task_attachment_context(
            db_session,
            task_id=task.id,
            company_id=company.id,
            storage=FakeParsedStorage(objects),
        )


def test_legacy_task_without_company_or_attachments_has_empty_context(
    db_session: Session, test_user
) -> None:
    task = create_task(db_session, user_id=test_user.id, question="hello")
    assert task.company_id is None
    result = build_task_attachment_context(
        db_session, task_id=task.id, company_id=None, storage=None
    )
    assert result.planner_payload == []
    assert result.selection_manifest == {
        "attachment_count": 0,
        "selected_char_count": 0,
        "items": [],
    }


def test_attachment_context_rejects_missing_company_before_storage_access(
    db_session: Session, test_user, monkeypatch
) -> None:
    company = _company_scope(db_session, test_user.id)
    version, objects = _create_ready_parse_result(
        db_session,
        user_id=test_user.id,
        company_id=company.id,
        suffix="d",
        text="private attachment",
    )
    task = create_task(
        db_session,
        user_id=test_user.id,
        question="分析附件",
        company_id=company.id,
        input_artifact_version_ids=[version.id],
    )
    storage = FakeParsedStorage(objects)

    def unexpected_download(**kwargs):
        pytest.fail("missing company scope must not read object storage")

    monkeypatch.setattr(storage, "download_parsed_object", unexpected_download)
    with pytest.raises(
        AttachmentContextError, match="attachment_company_scope_missing"
    ):
        build_task_attachment_context(
            db_session, task_id=task.id, company_id=None, storage=storage
        )
