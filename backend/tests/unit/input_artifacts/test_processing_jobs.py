from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.session import set_tenant_scope
from app.modules.identity.models import User
from app.modules.input_artifacts.models import (
    ArtifactParseResult,
    ArtifactProcessingAttempt,
    ArtifactProcessingJob,
    ArtifactProcessingOutboxEvent,
    InputArtifactVersion,
)
from app.modules.input_artifacts.processing.processing_jobs import (
    claim_parse_job_for_processing,
    claim_scan_job_for_processing,
    complete_parse_job_processing,
    complete_scan_job_processing,
    fail_parse_job_processing,
    fail_scan_job_processing,
    reject_scan_job_processing,
    recover_expired_scan_job,
)
from app.modules.input_artifacts.processing.processing_outbox import (
    publish_artifact_processing_event,
)
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _company_scope(db: Session, user: User) -> Company:
    company = Company(name="artifact-processing-job-company")
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
    return company


def _received_version(
    db: Session,
    *,
    company: Company,
    user: User,
) -> int:
    return create_received_input_artifact_version(
        db,
        company_id=company.id,
        uploaded_by_user_id=user.id,
        kind="attachment",
        original_filename="sales.csv",
        raw_object_key=f"input-artifacts/quarantine/{company.id}/sales.csv",
        byte_size=1024,
        sha256="a" * 64,
        commit=False,
    ).id


def test_processing_job_starts_as_a_durable_queued_scan(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-1",
    )
    db_session.add(job)
    db_session.flush()

    assert job.status == "queued"
    assert job.attempt_generation == 0
    assert job.retry_count == 0
    assert job.execution_id is None
    assert job.lease_expires_at is None
    assert job.finished_at is None


def test_processing_job_rejects_duplicate_stage_for_one_version(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    db_session.add_all(
        (
            ArtifactProcessingJob(
                company_id=company.id,
                artifact_version_id=version_id,
                stage="scan",
                trace_request_id="trace-processing-job-1",
            ),
            ArtifactProcessingJob(
                company_id=company.id,
                artifact_version_id=version_id,
                stage="scan",
                trace_request_id="trace-processing-job-2",
            ),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_processing_job_rejects_terminal_state_without_terminal_fields(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        status="failed",
        trace_request_id="trace-processing-job-1",
    )
    db_session.add(job)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_claiming_a_queued_scan_job_creates_its_first_running_attempt(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-claim-1",
    )
    db_session.add(job)
    db_session.flush()

    claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
        lease_seconds=60,
    )

    assert claim is not None
    assert claim.company_id == company.id
    assert claim.job_id == job.id
    assert claim.artifact_version_id == version_id
    assert claim.generation == 1
    assert claim.execution_id

    db_session.refresh(job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = db_session.query(ArtifactProcessingAttempt).one()
    assert version is not None
    assert job.status == "running"
    assert job.attempt_generation == 1
    assert job.execution_id == claim.execution_id
    assert job.lease_expires_at is not None
    assert version.status == "scanning"
    assert attempt.artifact_version_id == version_id
    assert attempt.stage == "scan"
    assert attempt.attempt_number == 1
    assert attempt.status == "running"
    assert attempt.processor_name == "clamav"
    assert attempt.processor_version == "1.4.2"
    assert attempt.trace_id == job.trace_request_id


def test_current_scan_job_lease_prevents_a_second_attempt(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-claim-2",
    )
    db_session.add(job)
    db_session.flush()

    first_claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    second_claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )

    assert first_claim is not None
    assert second_claim is None
    assert db_session.query(ArtifactProcessingAttempt).count() == 1


def test_scan_job_is_not_claimed_before_its_retry_time(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        available_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        trace_request_id="trace-processing-job-claim-3",
    )
    db_session.add(job)
    db_session.commit()

    claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )

    assert claim is None
    db_session.refresh(job)
    assert job.status == "queued"
    assert db_session.query(ArtifactProcessingAttempt).count() == 0


@pytest.mark.parametrize(
    ("processor_name", "processor_version"),
    [
        (" ", "1.4.2"),
        ("c" * 65, "1.4.2"),
        ("clamav", " "),
        ("clamav", "v" * 65),
    ],
)
def test_claim_rejects_invalid_processor_identity(
    db_session: Session,
    test_user: User,
    processor_name: str,
    processor_version: str,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-invalid-processor",
    )
    db_session.add(job)
    db_session.flush()

    with pytest.raises(ValueError, match="processor"):
        claim_scan_job_for_processing(
            db_session,
            job_id=job.id,
            expected_dispatch_generation=1,
            processor_name=processor_name,
            processor_version=processor_version,
        )


def test_stale_dispatch_generation_cannot_claim_a_queued_scan_job(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-stale-dispatch",
    )
    db_session.add(job)
    db_session.commit()

    assert (
        claim_scan_job_for_processing(
            db_session,
            job_id=job.id,
            expected_dispatch_generation=2,
            processor_name="clamav",
            processor_version="1.4.2",
        )
        is None
    )
    claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )

    assert claim is not None
    assert claim.generation == 1


def test_expired_first_scan_attempt_is_requeued_with_second_dispatch(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-recovery-1",
    )
    db_session.add(job)
    db_session.commit()
    claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert claim is not None

    db_session.refresh(job)
    job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    before_recovery = datetime.now(timezone.utc)

    recovery = recover_expired_scan_job(db_session, job_id=job.id)

    after_recovery = datetime.now(timezone.utc)
    assert recovery is not None
    assert recovery.outcome == "requeued"
    assert recovery.dispatch_generation == 2
    db_session.refresh(job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = db_session.query(ArtifactProcessingAttempt).one()
    event = db_session.query(ArtifactProcessingOutboxEvent).one()
    assert version is not None
    assert job.status == "queued"
    assert job.retry_count == 1
    assert job.execution_id is None
    assert job.lease_expires_at is None
    assert job.last_error_code == "worker_lease_expired"
    assert job.available_at >= before_recovery + timedelta(seconds=2)
    assert job.available_at <= after_recovery + timedelta(seconds=2)
    assert version.status == "scanning"
    assert attempt.status == "failed"
    assert attempt.error_code == "worker_lease_expired"
    assert attempt.retry_disposition == "scheduled"
    assert attempt.next_retry_at == job.available_at
    assert event.dispatch_generation == 2
    assert event.status == "pending"


def test_expired_third_scan_attempt_fails_without_new_dispatch(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    version = db_session.get(InputArtifactVersion, version_id)
    assert version is not None
    version.status = "scanning"
    version.status_changed_at = datetime.now(timezone.utc)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        status="running",
        attempt_generation=3,
        retry_count=2,
        max_attempts=3,
        execution_id=str(uuid4()),
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        trace_request_id="trace-processing-job-recovery-3",
    )
    attempt = ArtifactProcessingAttempt(
        artifact_version_id=version_id,
        stage="scan",
        attempt_number=3,
        status="running",
        processor_name="clamav",
        processor_version="1.4.2",
        trace_id=job.trace_request_id,
    )
    db_session.add_all((job, attempt))
    db_session.commit()

    recovery = recover_expired_scan_job(db_session, job_id=job.id)

    assert recovery is not None
    assert recovery.outcome == "failed"
    assert recovery.dispatch_generation is None
    db_session.refresh(job)
    db_session.refresh(version)
    db_session.refresh(attempt)
    assert job.status == "failed"
    assert job.retry_count == 3
    assert job.execution_id is None
    assert job.lease_expires_at is None
    assert job.last_error_code == "scan_retry_exhausted"
    assert job.finished_at is not None
    assert version.status == "failed"
    assert version.status_reason_code == "scan_retry_exhausted"
    assert attempt.status == "failed"
    assert attempt.error_code == "worker_lease_expired"
    assert attempt.retry_disposition == "exhausted"
    assert attempt.next_retry_at is None
    assert db_session.query(ArtifactProcessingOutboxEvent).count() == 0


def test_expired_scan_attempt_is_published_and_claimed_by_the_next_worker(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-retry-worker",
    )
    db_session.add(job)
    db_session.commit()

    first_claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert first_claim is not None

    db_session.refresh(job)
    job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    recovery = recover_expired_scan_job(db_session, job_id=job.id)

    assert recovery is not None
    assert recovery.dispatch_generation == 2
    event = db_session.query(ArtifactProcessingOutboxEvent).one()
    delivered: list[tuple[int, int, int]] = []

    assert publish_artifact_processing_event(
        db_session,
        event_id=event.id,
        enqueue=lambda company_id, job_id, dispatch_generation: (
            delivered.append((company_id, job_id, dispatch_generation))
            or SimpleNamespace(id="broker-message-retry-2")
        ),
    )
    assert delivered == [(company.id, job.id, 2)]
    db_session.refresh(event)
    assert event.status == "published"

    db_session.refresh(job)
    job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    second_claim = claim_scan_job_for_processing(
        db_session,
        job_id=job.id,
        expected_dispatch_generation=2,
        processor_name="clamav",
        processor_version="1.4.2",
    )

    assert second_claim is not None
    assert second_claim.generation == 2
    assert second_claim.execution_id != first_claim.execution_id
    attempts = (
        db_session.query(ArtifactProcessingAttempt)
        .order_by(ArtifactProcessingAttempt.attempt_number)
        .all()
    )
    assert [(attempt.attempt_number, attempt.status) for attempt in attempts] == [
        (1, "failed"),
        (2, "running"),
    ]


def test_only_current_scan_worker_can_complete_and_schedule_parse(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-completion-fence",
    )
    db_session.add(scan_job)
    db_session.commit()

    first_claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert first_claim is not None

    db_session.refresh(scan_job)
    scan_job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    recovery = recover_expired_scan_job(db_session, job_id=scan_job.id)
    assert recovery is not None

    db_session.refresh(scan_job)
    scan_job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    second_claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=2,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert second_claim is not None

    assert not complete_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=first_claim.execution_id,
        expected_generation=first_claim.generation,
    )
    db_session.refresh(scan_job)
    assert scan_job.status == "running"
    assert scan_job.execution_id == second_claim.execution_id
    assert scan_job.attempt_generation == 2
    assert (
        db_session.query(ArtifactProcessingJob)
        .filter(ArtifactProcessingJob.stage == "parse")
        .count()
        == 0
    )

    assert complete_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=second_claim.execution_id,
        expected_generation=second_claim.generation,
    )

    db_session.refresh(scan_job)
    version = db_session.get(InputArtifactVersion, version_id)
    parse_job = (
        db_session.query(ArtifactProcessingJob)
        .filter(ArtifactProcessingJob.stage == "parse")
        .one()
    )
    parse_event = (
        db_session.query(ArtifactProcessingOutboxEvent)
        .filter(ArtifactProcessingOutboxEvent.job_id == parse_job.id)
        .one()
    )
    second_attempt = (
        db_session.query(ArtifactProcessingAttempt)
        .filter(
            ArtifactProcessingAttempt.stage == "scan",
            ArtifactProcessingAttempt.attempt_number == 2,
        )
        .one()
    )
    assert version is not None
    assert scan_job.status == "succeeded"
    assert scan_job.execution_id is None
    assert scan_job.lease_expires_at is None
    assert scan_job.finished_at is not None
    assert second_attempt.status == "succeeded"
    assert second_attempt.finished_at is not None
    assert version.status == "parsing"
    assert parse_job.status == "queued"
    assert parse_job.attempt_generation == 0
    assert parse_event.dispatch_generation == 1
    assert parse_event.status == "pending"


def test_parse_job_can_be_claimed_after_current_scan_worker_completes(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-processing-job-parse-claim",
    )
    db_session.add(scan_job)
    db_session.commit()

    scan_claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert scan_claim is not None
    assert complete_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=scan_claim.execution_id,
        expected_generation=scan_claim.generation,
    )

    parse_job = (
        db_session.query(ArtifactProcessingJob)
        .filter(ArtifactProcessingJob.stage == "parse")
        .one()
    )
    parse_claim = claim_parse_job_for_processing(
        db_session,
        job_id=parse_job.id,
        expected_dispatch_generation=1,
        processor_name="document-parser",
        processor_version="2.0.0",
    )

    assert parse_claim is not None
    assert parse_claim.generation == 1
    db_session.refresh(parse_job)
    version = db_session.get(InputArtifactVersion, version_id)
    parse_attempt = (
        db_session.query(ArtifactProcessingAttempt)
        .filter(ArtifactProcessingAttempt.stage == "parse")
        .one()
    )
    assert version is not None
    assert parse_job.status == "running"
    assert parse_job.execution_id == parse_claim.execution_id
    assert version.status == "parsing"
    assert parse_attempt.attempt_number == 1
    assert parse_attempt.status == "running"
    assert parse_attempt.processor_name == "document-parser"


def test_current_parse_worker_publishes_its_immutable_result_and_marks_ready(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-parse-completion-success",
    )
    db_session.add(scan_job)
    db_session.commit()
    scan_claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert scan_claim is not None
    assert complete_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=scan_claim.execution_id,
        expected_generation=scan_claim.generation,
    )
    parse_job = db_session.query(ArtifactProcessingJob).filter_by(stage="parse").one()
    parse_claim = claim_parse_job_for_processing(
        db_session,
        job_id=parse_job.id,
        expected_dispatch_generation=1,
        processor_name="document-parser",
        processor_version="2.0.0",
    )
    assert parse_claim is not None

    assert complete_parse_job_processing(
        db_session,
        job_id=parse_job.id,
        execution_id=parse_claim.execution_id,
        expected_generation=parse_claim.generation,
        result_schema_version="artifact-parse-result/v1",
        manifest_object_key=f"input-artifacts/parsed/{version_id}/manifest.json",
        manifest_sha256="b" * 64,
        extracted_text_object_key=f"input-artifacts/parsed/{version_id}/text.txt",
        extracted_text_sha256="c" * 64,
        extracted_text_char_count=42,
    )

    db_session.refresh(parse_job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = (
        db_session.query(ArtifactProcessingAttempt)
        .filter_by(artifact_version_id=version_id, stage="parse", attempt_number=1)
        .one()
    )
    result = db_session.query(ArtifactParseResult).one()
    assert version is not None
    assert parse_job.status == "succeeded"
    assert parse_job.execution_id is None
    assert parse_job.lease_expires_at is None
    assert attempt.status == "succeeded"
    assert result.processing_attempt_id == attempt.id
    assert result.manifest_sha256 == "b" * 64
    assert version.status == "ready"
    assert version.active_parse_result_id == result.id


def test_wrong_parse_worker_cannot_publish_a_result_or_mark_ready(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-parse-completion-fence",
    )
    db_session.add(scan_job)
    db_session.commit()
    scan_claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert scan_claim is not None
    assert complete_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=scan_claim.execution_id,
        expected_generation=scan_claim.generation,
    )
    parse_job = db_session.query(ArtifactProcessingJob).filter_by(stage="parse").one()
    parse_claim = claim_parse_job_for_processing(
        db_session,
        job_id=parse_job.id,
        expected_dispatch_generation=1,
        processor_name="document-parser",
        processor_version="2.0.0",
    )
    assert parse_claim is not None

    assert not complete_parse_job_processing(
        db_session,
        job_id=parse_job.id,
        execution_id="stale-worker-execution-id",
        expected_generation=parse_claim.generation,
        result_schema_version="artifact-parse-result/v1",
        manifest_object_key=f"input-artifacts/parsed/{version_id}/manifest.json",
        manifest_sha256="b" * 64,
        extracted_text_object_key=None,
        extracted_text_sha256=None,
        extracted_text_char_count=0,
    )

    db_session.refresh(parse_job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = (
        db_session.query(ArtifactProcessingAttempt)
        .filter_by(artifact_version_id=version_id, stage="parse", attempt_number=1)
        .one()
    )
    assert version is not None
    assert parse_job.status == "running"
    assert parse_job.execution_id == parse_claim.execution_id
    assert version.status == "parsing"
    assert attempt.status == "running"
    assert db_session.query(ArtifactParseResult).count() == 0


def test_current_parse_worker_can_record_a_terminal_parse_failure(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    version = db_session.get(InputArtifactVersion, version_id)
    assert version is not None
    version.status = "parsing"
    version.status_changed_at = datetime.now(timezone.utc)
    parse_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="parse",
        status="running",
        attempt_generation=1,
        execution_id=str(uuid4()),
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        trace_request_id="trace-parse-failure-current-worker",
    )
    parse_attempt = ArtifactProcessingAttempt(
        artifact_version_id=version_id,
        stage="parse",
        attempt_number=1,
        status="running",
        processor_name="document-parser",
        processor_version="2.0.0",
        trace_id=parse_job.trace_request_id,
    )
    db_session.add_all((parse_job, parse_attempt))
    db_session.commit()

    assert fail_parse_job_processing(
        db_session,
        job_id=parse_job.id,
        execution_id=parse_job.execution_id,
        expected_generation=1,
        error_code="parser_invalid_structure",
    )

    db_session.refresh(parse_job)
    db_session.refresh(parse_attempt)
    db_session.refresh(version)
    assert parse_job.status == "failed"
    assert parse_job.execution_id is None
    assert parse_job.lease_expires_at is None
    assert parse_job.last_error_code == "parser_invalid_structure"
    assert parse_attempt.status == "failed"
    assert parse_attempt.error_code == "parser_invalid_structure"
    assert parse_attempt.retry_disposition == "not_retryable"
    assert parse_attempt.next_retry_at is None
    assert version.status == "failed"
    assert version.status_reason_code == "parser_invalid_structure"
    assert db_session.query(ArtifactParseResult).count() == 0


def test_wrong_parse_worker_cannot_record_a_terminal_failure(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    version = db_session.get(InputArtifactVersion, version_id)
    assert version is not None
    version.status = "parsing"
    version.status_changed_at = datetime.now(timezone.utc)
    parse_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="parse",
        status="running",
        attempt_generation=1,
        execution_id=str(uuid4()),
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        trace_request_id="trace-parse-failure-fence",
    )
    parse_attempt = ArtifactProcessingAttempt(
        artifact_version_id=version_id,
        stage="parse",
        attempt_number=1,
        status="running",
        processor_name="document-parser",
        processor_version="2.0.0",
        trace_id=parse_job.trace_request_id,
    )
    db_session.add_all((parse_job, parse_attempt))
    db_session.commit()

    assert not fail_parse_job_processing(
        db_session,
        job_id=parse_job.id,
        execution_id="stale-worker-execution-id",
        expected_generation=1,
        error_code="parser_invalid_structure",
    )

    db_session.refresh(parse_job)
    db_session.refresh(parse_attempt)
    db_session.refresh(version)
    assert parse_job.status == "running"
    assert parse_job.execution_id is not None
    assert parse_attempt.status == "running"
    assert version.status == "parsing"


def test_current_scan_worker_can_reject_an_unsafe_artifact(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-scan-rejection-success",
    )
    db_session.add(scan_job)
    db_session.commit()
    claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert claim is not None

    assert reject_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=claim.execution_id,
        expected_generation=claim.generation,
        reason_code="malware_detected",
    )

    db_session.refresh(scan_job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = db_session.query(ArtifactProcessingAttempt).one()
    assert version is not None
    assert scan_job.status == "rejected"
    assert scan_job.execution_id is None
    assert scan_job.lease_expires_at is None
    assert scan_job.last_error_code == "malware_detected"
    assert attempt.status == "rejected"
    assert attempt.error_code == "malware_detected"
    assert version.status == "rejected"
    assert version.status_reason_code == "malware_detected"


def test_wrong_scan_worker_cannot_reject_an_artifact(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-scan-rejection-fence",
    )
    db_session.add(scan_job)
    db_session.commit()
    claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert claim is not None

    assert not reject_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id="stale-worker-execution-id",
        expected_generation=claim.generation,
        reason_code="malware_detected",
    )

    db_session.refresh(scan_job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = db_session.query(ArtifactProcessingAttempt).one()
    assert version is not None
    assert scan_job.status == "running"
    assert scan_job.execution_id == claim.execution_id
    assert attempt.status == "running"
    assert version.status == "scanning"


def test_retryable_scan_failure_schedules_the_next_outbox_dispatch(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-scan-failure-retry",
    )
    db_session.add(scan_job)
    db_session.commit()
    claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert claim is not None

    outcome = fail_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=claim.execution_id,
        expected_generation=claim.generation,
        error_code="scanner_unavailable",
        retryable=True,
    )

    assert outcome is not None
    assert outcome.outcome == "requeued"
    assert outcome.dispatch_generation == 2
    db_session.refresh(scan_job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = db_session.query(ArtifactProcessingAttempt).one()
    event = db_session.query(ArtifactProcessingOutboxEvent).one()
    assert version is not None
    assert scan_job.status == "queued"
    assert scan_job.retry_count == 1
    assert scan_job.execution_id is None
    assert scan_job.last_error_code == "scanner_unavailable"
    assert version.status == "scanning"
    assert attempt.status == "failed"
    assert attempt.retry_disposition == "scheduled"
    assert attempt.next_retry_at == scan_job.available_at
    assert event.dispatch_generation == 2


def test_non_retryable_scan_failure_marks_the_version_failed(
    db_session: Session,
    test_user: User,
) -> None:
    company = _company_scope(db_session, test_user)
    version_id = _received_version(db_session, company=company, user=test_user)
    scan_job = ArtifactProcessingJob(
        company_id=company.id,
        artifact_version_id=version_id,
        stage="scan",
        trace_request_id="trace-scan-failure-terminal",
    )
    db_session.add(scan_job)
    db_session.commit()
    claim = claim_scan_job_for_processing(
        db_session,
        job_id=scan_job.id,
        expected_dispatch_generation=1,
        processor_name="clamav",
        processor_version="1.4.2",
    )
    assert claim is not None

    outcome = fail_scan_job_processing(
        db_session,
        job_id=scan_job.id,
        execution_id=claim.execution_id,
        expected_generation=claim.generation,
        error_code="scanner_result_invalid",
        retryable=False,
    )

    assert outcome is not None
    assert outcome.outcome == "failed"
    assert outcome.dispatch_generation is None
    db_session.refresh(scan_job)
    version = db_session.get(InputArtifactVersion, version_id)
    attempt = db_session.query(ArtifactProcessingAttempt).one()
    assert version is not None
    assert scan_job.status == "failed"
    assert scan_job.last_error_code == "scanner_result_invalid"
    assert attempt.status == "failed"
    assert attempt.error_code == "scanner_result_invalid"
    assert attempt.retry_disposition == "not_retryable"
    assert version.status == "failed"
    assert version.status_reason_code == "scanner_result_invalid"
