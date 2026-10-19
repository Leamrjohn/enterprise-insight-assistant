"""Build a bounded, task-scoped attachment context for the Planner.

The returned prompt payload is runtime-only.  It must never be added to a
workflow checkpoint, task result, event payload, or normal application log.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.modules.input_artifacts.models import (
    ArtifactParseResult,
    InputArtifact,
    InputArtifactVersion,
)
from app.modules.input_artifacts.processing.processing_storage import ArtifactProcessingStorage
from app.modules.workflow.models import AnalysisTaskInputArtifactVersion
from sqlalchemy.orm import Session


class AttachmentContextError(RuntimeError):
    """A frozen attachment cannot safely become model context."""


@dataclass(frozen=True, slots=True)
class AttachmentContextLimits:
    max_attachments: int = 20
    max_chars_per_attachment: int = 4_000
    max_total_chars: int = 12_000

    def __post_init__(self) -> None:
        if min(
            self.max_attachments,
            self.max_chars_per_attachment,
            self.max_total_chars,
        ) < 1:
            raise ValueError("attachment context limits must be positive")


_DEFAULT_ATTACHMENT_CONTEXT_LIMITS = AttachmentContextLimits()


@dataclass(frozen=True, slots=True)
class TaskAttachmentContext:
    """Prompt content plus durable-safe selection metadata.

    ``planner_payload`` contains untrusted extracted text and is deliberately
    excluded from all persistence.  ``selection_manifest`` contains metadata
    only and can be persisted later if an audit projection needs it.
    """

    planner_payload: list[dict[str, Any]]
    selection_manifest: dict[str, Any]


def build_task_attachment_context(
    db: Session,
    *,
    task_id: int,
    company_id: int,
    storage: ArtifactProcessingStorage | None,
    limits: AttachmentContextLimits = _DEFAULT_ATTACHMENT_CONTEXT_LIMITS,
) -> TaskAttachmentContext:
    """Load exactly the versions frozen for one task and verify their outputs."""
    frozen_ids = [
        artifact_version_id
        for (artifact_version_id,) in (
            db.query(AnalysisTaskInputArtifactVersion.artifact_version_id)
            .filter(AnalysisTaskInputArtifactVersion.task_id == task_id)
            .order_by(AnalysisTaskInputArtifactVersion.position)
            .all()
        )
    ]
    if len(frozen_ids) > limits.max_attachments:
        raise AttachmentContextError("attachment_scope_exceeds_context_limit")
    if not frozen_ids:
        return TaskAttachmentContext(
            planner_payload=[],
            selection_manifest={"attachment_count": 0, "selected_char_count": 0, "items": []},
        )
    if storage is None:
        raise AttachmentContextError("attachment_storage_unavailable")

    rows = (
        db.query(
            AnalysisTaskInputArtifactVersion.position,
            InputArtifactVersion,
            InputArtifact,
            ArtifactParseResult,
        )
        .join(
            InputArtifactVersion,
            InputArtifactVersion.id
            == AnalysisTaskInputArtifactVersion.artifact_version_id,
        )
        .join(InputArtifact, InputArtifact.id == InputArtifactVersion.artifact_id)
        .join(
            ArtifactParseResult,
            ArtifactParseResult.id == InputArtifactVersion.active_parse_result_id,
        )
        .filter(
            AnalysisTaskInputArtifactVersion.task_id == task_id,
            InputArtifact.company_id == company_id,
            InputArtifactVersion.status == "ready",
            ArtifactParseResult.artifact_version_id == InputArtifactVersion.id,
        )
        .order_by(AnalysisTaskInputArtifactVersion.position)
        .all()
    )
    if [version.id for _, version, _, _ in rows] != frozen_ids:
        raise AttachmentContextError("attachment_scope_is_no_longer_usable")

    payload: list[dict[str, Any]] = []
    manifest_items: list[dict[str, Any]] = []
    remaining = limits.max_total_chars
    with TemporaryDirectory(prefix="task-attachment-context-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        for position, version, _artifact, parse_result in rows:
            manifest = _read_verified_manifest(
                storage=storage,
                parse_result=parse_result,
                destination_path=temporary_path / f"{position}-manifest.json",
            )
            text = _read_verified_extracted_text(
                storage=storage,
                parse_result=parse_result,
                destination_path=temporary_path / f"{position}-extracted.txt",
            )
            selected = text[: limits.max_chars_per_attachment]
            selected = selected[:remaining]
            remaining -= len(selected)
            was_truncated = len(selected) < len(text)
            if selected:
                payload.append(
                    {
                        "artifact_version_id": version.id,
                        "original_filename": version.original_filename,
                        "content_trust_level": "untrusted",
                        "extracted_text": selected,
                    }
                )
            manifest_items.append(
                {
                    "artifact_version_id": version.id,
                    "parse_result_id": parse_result.id,
                    "position": position,
                    "source_format": manifest.get("source_format"),
                    "content_trust_level": "untrusted",
                    "content_verification": manifest.get("content_verification"),
                    "extracted_text_char_count": len(text),
                    "selected_char_count": len(selected),
                    "truncated": was_truncated,
                    "selection_reason": (
                        "selected" if selected else "global_context_budget_exhausted"
                    ),
                }
            )
    return TaskAttachmentContext(
        planner_payload=payload,
        selection_manifest={
            "attachment_count": len(rows),
            "selected_char_count": sum(item["selected_char_count"] for item in manifest_items),
            "items": manifest_items,
        },
    )


def _read_verified_manifest(
    *,
    storage: ArtifactProcessingStorage,
    parse_result: ArtifactParseResult,
    destination_path: Path,
) -> dict[str, Any]:
    stored = storage.download_parsed_object(
        object_key=parse_result.manifest_object_key,
        destination_path=destination_path,
    )
    if stored.sha256_hex != parse_result.manifest_sha256:
        raise AttachmentContextError("attachment_manifest_checksum_mismatch")
    try:
        payload = json.loads(destination_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttachmentContextError("attachment_manifest_invalid") from exc
    if not isinstance(payload, dict) or payload.get("content_trust_level") != "untrusted":
        raise AttachmentContextError("attachment_manifest_untrusted_contract_missing")
    return payload


def _read_verified_extracted_text(
    *,
    storage: ArtifactProcessingStorage,
    parse_result: ArtifactParseResult,
    destination_path: Path,
) -> str:
    if parse_result.extracted_text_object_key is None:
        if parse_result.extracted_text_char_count != 0:
            raise AttachmentContextError("attachment_text_contract_invalid")
        return ""
    if parse_result.extracted_text_sha256 is None:
        raise AttachmentContextError("attachment_text_contract_invalid")
    stored = storage.download_parsed_object(
        object_key=parse_result.extracted_text_object_key,
        destination_path=destination_path,
    )
    if stored.sha256_hex != parse_result.extracted_text_sha256:
        raise AttachmentContextError("attachment_text_checksum_mismatch")
    try:
        text = destination_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AttachmentContextError("attachment_text_invalid") from exc
    if len(text) != parse_result.extracted_text_char_count:
        raise AttachmentContextError("attachment_text_char_count_mismatch")
    return text
