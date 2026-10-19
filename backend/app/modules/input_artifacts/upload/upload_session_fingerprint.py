"""Canonical idempotency fingerprint for direct-upload initiation."""

import hashlib
import json

from app.modules.input_artifacts.storage import DeclaredInputArtifactUpload


def build_direct_upload_session_fingerprint(
    *,
    company_id: int,
    submitted_by_user_id: int,
    conversation_id: int,
    declared_upload: DeclaredInputArtifactUpload,
    upload_policy_version: str,
) -> str:
    payload = {
        "fingerprint_version": 1,
        "company_id": company_id,
        "submitted_by_user_id": submitted_by_user_id,
        "conversation_id": conversation_id,
        "purpose": "conversation_attachment",
        "filename": declared_upload.original_filename,
        "byte_size": declared_upload.byte_size,
        "declared_mime_type": declared_upload.declared_mime_type,
        "client_reported_sha256": declared_upload.client_reported_sha256,
        "upload_policy_version": upload_policy_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
