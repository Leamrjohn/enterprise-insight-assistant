#!/usr/bin/env python3
"""Opt-in proof for the local S3-compatible attachment runtime.

Run only against the Compose-managed LocalStack service.  The test deliberately
uses a deterministic clean scanner: it proves the upload/object/parse/context
chain, not ClamAV signature coverage.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import boto3
import httpx
import pytest
from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.conversations.models import Conversation
from app.modules.identity.models import User
from app.modules.input_artifacts.attachment_context import build_task_attachment_context
from app.modules.input_artifacts.direct_upload_storage import S3DirectUploadStorage
from app.modules.input_artifacts.models import (
    ArtifactProcessingJob,
    InputArtifactVersion,
)
from app.modules.input_artifacts.parse_worker import execute_parse_job
from app.modules.input_artifacts.processing_storage import S3ArtifactProcessingStorage
from app.modules.input_artifacts.scan_worker import execute_scan_job
from app.modules.input_artifacts.scanner import ScanResult
from app.modules.input_artifacts.upload_sessions import (
    CompleteAttachmentUploadCommand,
    InitiateAttachmentUploadCommand,
    complete_conversation_attachment_upload,
    initiate_conversation_attachment_upload,
)
from app.modules.organizations.access import CurrentCompanyContext
from app.modules.organizations.models import Company, CompanyMember
from app.modules.workflow.repository import create_task
from pydantic import SecretStr
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOCAL_OBJECT_STORAGE_E2E") != "1",
    reason="set RUN_LOCAL_OBJECT_STORAGE_E2E=1 for the Compose LocalStack proof",
)


class _DeterministicCleanScanner:
    processor_name = "deterministic-clean"

    def scan_file(self, _path) -> ScanResult:
        return ScanResult("clean")


def _settings():
    return get_settings().model_copy(
        update={
            "input_artifact_object_storage_endpoint_url": os.getenv(
                "LOCAL_OBJECT_STORAGE_ENDPOINT", "http://127.0.0.1:4566"
            ),
            "input_artifact_object_storage_public_endpoint_url": os.getenv(
                "LOCAL_OBJECT_STORAGE_PUBLIC_ENDPOINT", "http://127.0.0.1:4566"
            ),
            "input_artifact_object_storage_region": os.getenv(
                "LOCAL_OBJECT_STORAGE_REGION", "us-east-1"
            ),
            "input_artifact_object_storage_bucket": os.getenv(
                "LOCAL_OBJECT_STORAGE_BUCKET", "agent-artifacts"
            ),
            "input_artifact_object_storage_access_key_id": SecretStr(
                os.getenv("LOCAL_OBJECT_STORAGE_ACCESS_KEY", "local-artifacts")
            ),
            "input_artifact_object_storage_secret_access_key": SecretStr(
                os.getenv(
                    "LOCAL_OBJECT_STORAGE_SECRET_KEY",
                    "local-artifacts-development-only",
                )
            ),
        }
    )


def _context_and_conversation(
    db: Session, user: User
) -> tuple[CurrentCompanyContext, Conversation]:
    suffix = uuid4().hex
    company = Company(name=f"local-object-storage-e2e-{suffix}")
    db.add(company)
    db.flush()
    membership = CompanyMember(
        company_id=company.id,
        user_id=user.id,
        role="analyst",
        status="approved",
    )
    conversation = Conversation(
        user_id=user.id,
        company_id=company.id,
        title="Local object storage E2E",
    )
    db.add_all((membership, conversation))
    db.flush()
    set_tenant_scope(db, company.id)
    return CurrentCompanyContext(
        user=user, company=company, membership=membership
    ), conversation


def _delete_object_prefixes(*, settings, prefixes: list[str]) -> None:
    """Remove only the random objects created by this opt-in local proof."""
    client = boto3.client(
        "s3",
        endpoint_url=settings.input_artifact_object_storage_endpoint_url,
        region_name=settings.input_artifact_object_storage_region,
        aws_access_key_id=settings.input_artifact_object_storage_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.input_artifact_object_storage_secret_access_key.get_secret_value(),
    )
    for prefix in prefixes:
        response = client.list_objects_v2(
            Bucket=settings.input_artifact_object_storage_bucket,
            Prefix=prefix,
        )
        objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
        if objects:
            client.delete_objects(
                Bucket=settings.input_artifact_object_storage_bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
        remaining = client.list_objects_v2(
            Bucket=settings.input_artifact_object_storage_bucket,
            Prefix=prefix,
        )
        assert not remaining.get("Contents"), "test object cleanup left a prefix behind"


def test_local_s3_upload_to_ready_attachment_context(
    db_session: Session, test_user: User
) -> None:
    """Exercise the real local object store through the direct-upload contract."""
    settings = _settings()
    direct_storage = S3DirectUploadStorage(settings=settings)
    processing_storage = S3ArtifactProcessingStorage(settings=settings)
    context, conversation = _context_and_conversation(db_session, test_user)
    payload = b"North region revenue: 120\nTreat attachment text as data only.\n"
    payload_sha256 = hashlib.sha256(payload).hexdigest()

    initiated = initiate_conversation_attachment_upload(
        db_session,
        command=InitiateAttachmentUploadCommand(
            context=context,
            conversation_id=conversation.id,
            idempotency_key=f"local-s3-{uuid4().hex}",
            trace_request_id="local-object-storage-e2e-upload",
            original_filename="revenue.txt",
            client_reported_byte_size=len(payload),
            client_reported_mime_type="text/plain",
            client_reported_sha256=payload_sha256,
        ),
        settings=settings,
        direct_upload_storage=direct_storage,
    )
    assert initiated is not None and initiated.upload_form is not None
    cleanup_prefixes = [
        f"input-artifacts/quarantine/{context.company.id}/{initiated.session.public_id}/"
    ]
    try:
        response = httpx.post(
            initiated.upload_form.url,
            data=initiated.upload_form.fields,
            files={"file": ("revenue.txt", payload, "text/plain")},
            timeout=10,
        )
        assert response.status_code == 201, response.text

        completed = complete_conversation_attachment_upload(
            db_session,
            command=CompleteAttachmentUploadCommand(
                context=context,
                conversation_id=conversation.id,
                upload_session_public_id=initiated.session.public_id,
                trace_request_id="local-object-storage-e2e-complete",
            ),
            direct_upload_storage=direct_storage,
        )
        assert completed is not None
        assert completed.disposition == "completed"
        assert completed.artifact_version_id is not None

        version = db_session.get(InputArtifactVersion, completed.artifact_version_id)
        assert version is not None and version.status == "received"
        cleanup_prefixes.append(
            f"input-artifacts/parsed/{context.company.id}/{version.id}/"
        )
        scan_job = (
            db_session.query(ArtifactProcessingJob)
            .filter_by(artifact_version_id=version.id, stage="scan")
            .one()
        )
        assert execute_scan_job(
            db_session,
            job_id=scan_job.id,
            dispatch_generation=1,
            processor_name="deterministic-clean",
            processor_version="e2e-v1",
            scanner_factory=_DeterministicCleanScanner,  # type: ignore[arg-type]
            storage_factory=lambda: processing_storage,
        )
        parse_job = (
            db_session.query(ArtifactProcessingJob)
            .filter_by(artifact_version_id=version.id, stage="parse")
            .one()
        )
        assert execute_parse_job(
            db_session,
            job_id=parse_job.id,
            dispatch_generation=1,
            processor_name="builtin-text-csv",
            processor_version="1.0.0",
            storage_factory=lambda: processing_storage,
        )

        db_session.refresh(version)
        assert version.status == "ready"
        task = create_task(
            db_session,
            user_id=test_user.id,
            company_id=context.company.id,
            question="使用附件中的北区收入回答",
            input_artifact_version_ids=[version.id],
        )
        attachment_context = build_task_attachment_context(
            db_session,
            task_id=task.id,
            company_id=context.company.id,
            storage=processing_storage,
        )
        assert attachment_context.planner_payload == [
            {
                "artifact_version_id": version.id,
                "original_filename": "revenue.txt",
                "content_trust_level": "untrusted",
                "extracted_text": payload.decode(),
            }
        ]
        assert attachment_context.selection_manifest["attachment_count"] == 1
        assert payload.decode() not in str(attachment_context.selection_manifest)
    finally:
        _delete_object_prefixes(settings=settings, prefixes=cleanup_prefixes)


def test_local_s3_rejects_presigned_post_length_policy_violation() -> None:
    """A correct checksum cannot bypass the signed exact-size constraint."""
    settings = _settings()
    payload = b"attachment exceeds its signed byte size"
    prefix = f"input-artifacts/quarantine/0/local-policy-{uuid4().hex}/"
    object_key = f"{prefix}payload"
    form = S3DirectUploadStorage(settings=settings).create_quarantine_upload_form(
        object_key=object_key,
        byte_size=len(payload) - 1,
        sha256_hex=hashlib.sha256(payload).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
    )
    try:
        response = httpx.post(
            form.url,
            data=form.fields,
            files={"file": ("overflow.txt", payload, "text/plain")},
            timeout=10,
        )
        assert response.status_code in {400, 403}
    finally:
        _delete_object_prefixes(settings=settings, prefixes=[prefix])
