import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.modules.input_artifacts.models import ArtifactProcessingOutboxEvent
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

_FAILURE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True, slots=True)
class ClaimedArtifactProcessingPublication:
    event_id: int
    company_id: int
    job_id: int
    dispatch_generation: int
    execution_id: str
    generation: int
    trace_request_id: str


def claim_artifact_processing_event_for_publication(
    db: Session,
    *,
    event_id: int,
    lease_seconds: int = 30,
) -> ClaimedArtifactProcessingPublication | None:
    company_id = db.info.get("tenant_company_id")
    if not isinstance(company_id, int) or isinstance(company_id, bool):
        raise RuntimeError(  # noqa: TRY004 - Missing tenant session state, not a parameter type error.
            "artifact outbox publication requires a tenant-scoped session"
        )
    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds <= 0
    ):
        raise ValueError("lease_seconds must be a positive integer")

    now = datetime.now(timezone.utc)
    execution_id = str(uuid4())
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    event = (
        db.execute(
            update(ArtifactProcessingOutboxEvent)
            .where(
                ArtifactProcessingOutboxEvent.id == event_id,
                or_(
                    ArtifactProcessingOutboxEvent.status == "pending",
                    and_(
                        ArtifactProcessingOutboxEvent.status == "publishing",
                        ArtifactProcessingOutboxEvent.publish_lease_expires_at <= now,
                    ),
                ),
            )
            .values(
                status="publishing",
                publish_generation=ArtifactProcessingOutboxEvent.publish_generation + 1,
                publish_execution_id=execution_id,
                publish_lease_expires_at=lease_expires_at,
                last_error=None,
            )
            .returning(
                ArtifactProcessingOutboxEvent.id,
                ArtifactProcessingOutboxEvent.company_id,
                ArtifactProcessingOutboxEvent.job_id,
                ArtifactProcessingOutboxEvent.dispatch_generation,
                ArtifactProcessingOutboxEvent.publish_generation,
                ArtifactProcessingOutboxEvent.trace_request_id,
            )
            .execution_options(synchronize_session=False)
        )
        .mappings()
        .one_or_none()
    )
    if event is None:
        db.rollback()
        return None

    try:
        if event["company_id"] != company_id:
            raise RuntimeError("claimed outbox event is outside the tenant scope")
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ClaimedArtifactProcessingPublication(
        event["id"],
        company_id,
        event["job_id"],
        event["dispatch_generation"],
        execution_id,
        event["publish_generation"],
        event["trace_request_id"],
    )


def mark_artifact_processing_event_published(
    db: Session,
    *,
    claim: ClaimedArtifactProcessingPublication,
    broker_message_id: str,
) -> bool:
    company_id = db.info.get("tenant_company_id")
    if not isinstance(company_id, int) or isinstance(company_id, bool):
        raise RuntimeError(  # noqa: TRY004 - Missing tenant session state, not a parameter type error.
            "artifact outbox publication requires a tenant-scoped session"
        )
    if not isinstance(broker_message_id, str) or not (broker_message_id.strip()):
        raise ValueError("broker_message_id is empty")
    normalized_message_id = broker_message_id.strip()
    if not normalized_message_id or len(normalized_message_id) > 255:
        raise ValueError("broker_message_id is invalid")
    if company_id != claim.company_id:
        raise RuntimeError(
            "artifact outbox publication claim does not match the tenant scope"
        )
    now = datetime.now(timezone.utc)
    event = db.scalar(
        update(ArtifactProcessingOutboxEvent)
        .where(
            ArtifactProcessingOutboxEvent.status == "publishing",
            ArtifactProcessingOutboxEvent.id == claim.event_id,
            ArtifactProcessingOutboxEvent.company_id == claim.company_id,
            ArtifactProcessingOutboxEvent.publish_execution_id == claim.execution_id,
            ArtifactProcessingOutboxEvent.publish_generation == claim.generation,
            ArtifactProcessingOutboxEvent.publish_lease_expires_at > now,
        )
        .values(
            status="published",
            publish_execution_id=None,
            publish_lease_expires_at=None,
            broker_message_id=normalized_message_id,
            published_at=now,
            last_error=None,
            publish_attempt_count=ArtifactProcessingOutboxEvent.publish_attempt_count
            + 1,
        )
        .returning(ArtifactProcessingOutboxEvent)
        .execution_options(synchronize_session=False)
    )
    if event is None:
        db.rollback()
        return False

    try:
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def return_artifact_processing_event_to_pending(
    db: Session,
    *,
    claim: ClaimedArtifactProcessingPublication,
    failure_code: str,
) -> bool:
    company_id = db.info.get("tenant_company_id")
    if not isinstance(company_id, int) or isinstance(company_id, bool):
        raise RuntimeError(  # noqa: TRY004 - Missing tenant session state, not a parameter type error.
            "artifact outbox publication requires a tenant-scoped session"
        )
    if not isinstance(failure_code, str) or not (failure_code.strip()):
        raise ValueError("failure_code  is empty")
    normalized_failure_code = failure_code.strip()
    if not normalized_failure_code or len(normalized_failure_code) > 64:
        raise ValueError("failure_code is invalid")
    if not _FAILURE_CODE_PATTERN.fullmatch(normalized_failure_code):
        raise ValueError("failure_code is invalid")
    if company_id != claim.company_id:
        raise RuntimeError(
            "artifact outbox publication claim does not match the tenant scope"
        )
    now = datetime.now(timezone.utc)
    event = db.scalar(
        update(ArtifactProcessingOutboxEvent)
        .where(
            ArtifactProcessingOutboxEvent.status == "publishing",
            ArtifactProcessingOutboxEvent.id == claim.event_id,
            ArtifactProcessingOutboxEvent.company_id == claim.company_id,
            ArtifactProcessingOutboxEvent.publish_execution_id == claim.execution_id,
            ArtifactProcessingOutboxEvent.publish_generation == claim.generation,
            ArtifactProcessingOutboxEvent.publish_lease_expires_at > now,
        )
        .values(
            status="pending",
            publish_execution_id=None,
            publish_lease_expires_at=None,
            broker_message_id=None,
            published_at=None,
            last_error=normalized_failure_code,
            publish_attempt_count=ArtifactProcessingOutboxEvent.publish_attempt_count
            + 1,
        )
        .returning(ArtifactProcessingOutboxEvent)
        .execution_options(synchronize_session=False)
    )
    if event is None:
        db.rollback()
        return False
    try:
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def pending_artifact_processing_event_ids(
    db: Session,
    *,
    limit: int = 100,
) -> list[int]:
    events = db.scalars(
        select(ArtifactProcessingOutboxEvent)
        .where(ArtifactProcessingOutboxEvent.status == "pending")
        .order_by(ArtifactProcessingOutboxEvent.id.asc())
        .limit(limit)
    )
    ids = []
    for event in events:
        ids.append(event.id)
    return ids


def publish_artifact_processing_event(
    db: Session,
    *,
    event_id: int,
    enqueue: Callable[[int, int, int], object],
    lease_seconds: int = 30,
) -> bool:
    claim = claim_artifact_processing_event_for_publication(
        db,
        event_id=event_id,
        lease_seconds=lease_seconds,
    )
    if claim is None:
        return False
    try:
        async_result = enqueue(
            claim.company_id,
            claim.job_id,
            claim.dispatch_generation,
        )
    except Exception:  # noqa: BLE001 - Restore the claimed event after any broker failure.
        return_artifact_processing_event_to_pending(
            db,
            claim=claim,
            failure_code="broker_publish_failed",
        )
        return False
    broker_message_id = getattr(async_result, "id", None)
    if not isinstance(broker_message_id, str) or not broker_message_id.strip():
        return_artifact_processing_event_to_pending(
            db,
            claim=claim,
            failure_code="broker_publish_invalid_result",
        )
        return False
    return mark_artifact_processing_event_published(
        db,
        claim=claim,
        broker_message_id=broker_message_id,
    )
