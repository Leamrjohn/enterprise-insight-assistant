from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app.db.session import set_tenant_scope
from app.modules.identity.models import User
from app.modules.input_artifacts.models import ArtifactProcessingOutboxEvent
from app.modules.input_artifacts.processing.processing_outbox import (
    claim_artifact_processing_event_for_publication,
    mark_artifact_processing_event_published,
    pending_artifact_processing_event_ids,
    publish_artifact_processing_event,
    return_artifact_processing_event_to_pending,
)
from app.modules.input_artifacts.repository import (
    add_artifact_processing_job,
    add_artifact_processing_outbox_event,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _create_pending_event(
    db: Session,
    *,
    user: User,
) -> ArtifactProcessingOutboxEvent:
    company = Company(name="artifact-outbox-company")
    db.add(company)
    db.flush()
    db.add(
        CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role="analyst",
            status="approved",
        )
    )
    db.flush()
    set_tenant_scope(db, company.id)
    version = create_received_input_artifact_version(
        db,
        company_id=company.id,
        uploaded_by_user_id=user.id,
        kind="attachment",
        original_filename="sales.csv",
        raw_object_key=f"input-artifacts/quarantine/{company.id}/sales.csv",
        byte_size=1024,
        sha256="a" * 64,
        commit=False,
    )
    job = add_artifact_processing_job(
        db,
        company_id=company.id,
        artifact_version_id=version.id,
        stage="scan",
        max_attempts=3,
        trace_request_id="trace-artifact-outbox-job",
    )
    return add_artifact_processing_outbox_event(
        db,
        company_id=company.id,
        job_id=job.id,
        dispatch_generation=1,
        trace_request_id="trace-artifact-outbox-event",
    )


def test_outbox_events_are_unique_per_job_dispatch_generation(
    db_session: Session,
    test_user: User,
) -> None:
    first_event = _create_pending_event(db_session, user=test_user)

    second_event = add_artifact_processing_outbox_event(
        db_session,
        company_id=first_event.company_id,
        job_id=first_event.job_id,
        dispatch_generation=2,
        trace_request_id="trace-artifact-outbox-event-generation-2",
    )

    assert second_event.dispatch_generation == 2
    with pytest.raises(IntegrityError), db_session.begin_nested():
        add_artifact_processing_outbox_event(
            db_session,
            company_id=first_event.company_id,
            job_id=first_event.job_id,
            dispatch_generation=2,
            trace_request_id="trace-artifact-outbox-event-generation-2-duplicate",
        )


def test_claim_outbox_event_is_exclusive_until_lease_expires(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    assert pending_artifact_processing_event_ids(db_session) == [event.id]

    first_claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
        lease_seconds=30,
    )

    assert first_claim is not None
    assert first_claim.event_id == event.id
    assert first_claim.company_id == event.company_id
    assert first_claim.job_id == event.job_id
    assert first_claim.generation == 1
    db_session.refresh(event)
    assert event.status == "publishing"
    assert event.publish_execution_id == first_claim.execution_id
    assert event.publish_generation == first_claim.generation
    assert event.publish_lease_expires_at is not None
    assert event.publish_lease_expires_at > datetime.now(timezone.utc)
    assert pending_artifact_processing_event_ids(db_session) == []

    assert (
        claim_artifact_processing_event_for_publication(
            db_session,
            event_id=event.id,
            lease_seconds=30,
        )
        is None
    )


def test_expired_outbox_claim_is_replaced_by_a_new_generation(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    first_claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert first_claim is not None

    event.publish_lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    second_claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )

    assert second_claim is not None
    assert second_claim.generation == first_claim.generation + 1
    assert second_claim.execution_id != first_claim.execution_id
    db_session.refresh(event)
    assert event.status == "publishing"
    assert event.publish_execution_id == second_claim.execution_id
    assert event.publish_generation == second_claim.generation


def test_current_claim_marks_outbox_event_published(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert claim is not None

    assert mark_artifact_processing_event_published(
        db_session,
        claim=claim,
        broker_message_id=" broker-message-1 ",
    )

    db_session.refresh(event)
    assert event.status == "published"
    assert event.publish_execution_id is None
    assert event.publish_lease_expires_at is None
    assert event.broker_message_id == "broker-message-1"
    assert event.published_at is not None
    assert event.publish_attempt_count == 1


def test_stale_claim_cannot_publish_after_a_new_generation_claims_event(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    first_claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert first_claim is not None
    event.publish_lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    second_claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert second_claim is not None

    assert not mark_artifact_processing_event_published(
        db_session,
        claim=first_claim,
        broker_message_id="broker-message-stale",
    )
    db_session.refresh(event)
    assert event.status == "publishing"
    assert event.publish_execution_id == second_claim.execution_id
    assert event.publish_generation == second_claim.generation


def test_expired_claim_cannot_publish_without_a_new_claim(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert claim is not None
    event.publish_lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    assert not mark_artifact_processing_event_published(
        db_session,
        claim=claim,
        broker_message_id="broker-message-expired",
    )
    db_session.refresh(event)
    assert event.status == "publishing"
    assert event.broker_message_id is None


def test_claim_from_another_company_is_rejected_before_publishing(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert claim is not None
    other_company = Company(name="other-artifact-outbox-company")
    db_session.add(other_company)
    db_session.flush()
    set_tenant_scope(db_session, other_company.id)

    with pytest.raises(RuntimeError, match="tenant scope"):
        mark_artifact_processing_event_published(
            db_session,
            claim=claim,
            broker_message_id="broker-message-other-company",
        )


def test_current_claim_returns_outbox_event_to_pending_after_publish_failure(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert claim is not None

    assert return_artifact_processing_event_to_pending(
        db_session,
        claim=claim,
        failure_code="broker_publish_failed",
    )

    db_session.refresh(event)
    assert event.status == "pending"
    assert event.publish_execution_id is None
    assert event.publish_lease_expires_at is None
    assert event.publish_generation == claim.generation
    assert event.last_error == "broker_publish_failed"
    assert event.publish_attempt_count == 1
    assert pending_artifact_processing_event_ids(db_session) == [event.id]


def test_stale_claim_cannot_return_new_generation_to_pending(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    first_claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert first_claim is not None
    event.publish_lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    second_claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert second_claim is not None

    assert not return_artifact_processing_event_to_pending(
        db_session,
        claim=first_claim,
        failure_code="broker_publish_failed",
    )
    db_session.refresh(event)
    assert event.status == "publishing"
    assert event.publish_execution_id == second_claim.execution_id
    assert event.publish_generation == second_claim.generation


def test_expired_claim_cannot_return_event_to_pending(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert claim is not None
    event.publish_lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    assert not return_artifact_processing_event_to_pending(
        db_session,
        claim=claim,
        failure_code="broker_publish_failed",
    )
    db_session.refresh(event)
    assert event.status == "publishing"
    assert event.last_error is None


@pytest.mark.parametrize(
    "failure_code",
    ["", " ", "BrokerPublishFailed", "broker-publish-failed", "a" * 65],
)
def test_return_to_pending_rejects_non_safe_failure_codes(
    db_session: Session,
    test_user: User,
    failure_code: str,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    claim = claim_artifact_processing_event_for_publication(
        db_session,
        event_id=event.id,
    )
    assert claim is not None

    with pytest.raises(ValueError, match="failure_code"):
        return_artifact_processing_event_to_pending(
            db_session,
            claim=claim,
            failure_code=failure_code,
        )


@pytest.mark.parametrize("lease_seconds", [0, -1, True, "30"])
def test_claim_rejects_invalid_lease_seconds(
    db_session: Session,
    test_user: User,
    lease_seconds: object,
) -> None:
    event = _create_pending_event(db_session, user=test_user)

    with pytest.raises(ValueError, match="lease_seconds"):
        claim_artifact_processing_event_for_publication(
            db_session,
            event_id=event.id,
            lease_seconds=lease_seconds,  # type: ignore[arg-type]
        )


def test_publish_enqueues_claimed_job_and_marks_event_published(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)
    received_arguments: list[tuple[int, int, int]] = []

    def enqueue(company_id: int, job_id: int, dispatch_generation: int) -> object:
        received_arguments.append((company_id, job_id, dispatch_generation))
        return SimpleNamespace(id="broker-message-1")

    assert publish_artifact_processing_event(
        db_session,
        event_id=event.id,
        enqueue=enqueue,
    )

    db_session.refresh(event)
    assert received_arguments == [
        (event.company_id, event.job_id, event.dispatch_generation)
    ]
    assert event.status == "published"
    assert event.broker_message_id == "broker-message-1"
    assert event.publish_attempt_count == 1


def test_publish_returns_event_to_pending_when_enqueue_raises(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)

    def enqueue(_: int, __: int, ___: int) -> object:
        raise ConnectionError("broker unavailable")

    assert not publish_artifact_processing_event(
        db_session,
        event_id=event.id,
        enqueue=enqueue,
    )

    db_session.refresh(event)
    assert event.status == "pending"
    assert event.last_error == "broker_publish_failed"
    assert event.publish_attempt_count == 1


def test_publish_returns_event_to_pending_when_enqueue_returns_no_message_id(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)

    assert not publish_artifact_processing_event(
        db_session,
        event_id=event.id,
        enqueue=lambda _company_id, _job_id, _dispatch_generation: object(),
    )

    db_session.refresh(event)
    assert event.status == "pending"
    assert event.last_error == "broker_publish_invalid_result"
    assert event.publish_attempt_count == 1


def test_publish_returns_event_to_pending_when_enqueue_returns_blank_message_id(
    db_session: Session,
    test_user: User,
) -> None:
    event = _create_pending_event(db_session, user=test_user)

    assert not publish_artifact_processing_event(
        db_session,
        event_id=event.id,
        enqueue=lambda _company_id, _job_id, _dispatch_generation: SimpleNamespace(
            id="   "
        ),
    )

    db_session.refresh(event)
    assert event.status == "pending"
    assert event.last_error == "broker_publish_invalid_result"
    assert event.publish_attempt_count == 1
