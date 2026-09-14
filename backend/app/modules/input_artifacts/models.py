from datetime import datetime
from uuid import uuid4

from app.db.base import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class InputArtifact(Base):
    __tablename__ = "input_artifacts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('attachment', 'knowledge_document', 'dataset')",
            name="input_artifact_kind_values",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class InputArtifactVersion(Base):
    __tablename__ = "input_artifact_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received' , 'scanning' , 'parsing' , 'ready' , 'rejected' , 'failed')",
            name="status_values",
        ),
        CheckConstraint(
            "(status IN ('rejected', 'failed') AND status_reason_code IS NOT NULL) "
            "OR (status NOT IN ('rejected', 'failed') AND status_reason_code IS NULL)",
            name="status_reason_matches_status",
        ),
        CheckConstraint(
            "version_number>0",
            name="version_number_positive",
        ),
        CheckConstraint(
            "byte_size >= 0",
            name="byte_size_non_negative",
        ),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="sha256_lower_hex",
        ),
        UniqueConstraint(
            "artifact_id",
            "version_number",
            name="uq_input_artifact_versions_artifact_id_with_version_number",
        ),
        UniqueConstraint(
            "raw_object_key",
            name="uq_input_artifact_versions_raw_object_key",
        ),
        ForeignKeyConstraint(
            ["active_parse_result_id", "id"],
            [
                "artifact_parse_results.id",
                "artifact_parse_results.artifact_version_id",
            ],
            name="fk_input_artifact_version_active_parse_result_same_version",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    active_parse_result_id: Mapped[int | None] = mapped_column(
        nullable=True,
        index=True,
    )
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("input_artifacts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_extension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), server_default="received", nullable=False, index=True
    )
    status_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ArtifactProcessingAttempt(Base):
    __tablename__ = "artifact_processing_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IS NOT NULL AND status IN ('running','succeeded','failed','rejected')",
            name="status_values",
        ),
        CheckConstraint("stage IN ('scan','parse')", name="stage_values"),
        CheckConstraint("attempt_number>0", name="attempt_number_positive"),
        CheckConstraint(
            "retry_disposition IS NULL OR retry_disposition IN ('scheduled','not_retryable','exhausted')",
            name="retry_disposition_values",
        ),
        CheckConstraint(
            "COALESCE("
            "(retry_disposition IS NULL AND next_retry_at IS NULL)"
            " OR (retry_disposition = 'scheduled' AND next_retry_at IS NOT NULL)"
            " OR ("
            "retry_disposition IN ('not_retryable', 'exhausted') "
            "AND next_retry_at IS NULL"
            "), FALSE)",
            name="retry_schedule_matches_disposition",
        ),
        CheckConstraint(
            "(status ='running' AND finished_at IS NULL AND error_code IS NULL  AND retry_disposition IS NULL) "
            "OR (status = 'succeeded' AND finished_at IS NOT NULL AND error_code IS  NULL  AND retry_disposition IS NULL) "
            "OR (status = 'failed' AND finished_at IS NOT NULL AND error_code IS NOT NULL  AND retry_disposition IS NOT NULL AND retry_disposition IN('scheduled','not_retryable','exhausted'))"
            "OR (status = 'rejected' AND finished_at IS NOT NULL AND error_code IS NOT NULL  AND retry_disposition IS NULL AND stage = 'scan')",
            name="status_fields_match_status",
        ),
        UniqueConstraint(
            "artifact_version_id",
            "stage",
            "attempt_number",
            name="uq_artifact_version_id_stage_attempt_number",
        ),
        UniqueConstraint(
            "id",
            "artifact_version_id",
            name="uq_artifact_processing_attempt_id_version",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_version_id: Mapped[int] = mapped_column(
        ForeignKey("input_artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    processor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    processor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)


class ArtifactParseResult(Base):
    """Immutable, storage-backed output of one successful parse attempt."""

    __tablename__ = "artifact_parse_results"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(result_schema_version)) BETWEEN 1 AND 64",
            name="ck_artifact_parse_result_schema_version",
        ),
        CheckConstraint(
            "length(btrim(manifest_object_key)) BETWEEN 1 AND 512",
            name="ck_artifact_parse_result_manifest_object_key",
        ),
        CheckConstraint(
            "manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_artifact_parse_result_manifest_sha256",
        ),
        CheckConstraint(
            "extracted_text_char_count >= 0",
            name="ck_artifact_parse_result_extracted_text_char_count",
        ),
        CheckConstraint(
            "(extracted_text_object_key IS NULL "
            "AND extracted_text_sha256 IS NULL "
            "AND extracted_text_char_count = 0) "
            "OR (extracted_text_object_key IS NOT NULL "
            "AND extracted_text_sha256 IS NOT NULL)",
            name="ck_artifact_parse_result_extracted_text_fields",
        ),
        CheckConstraint(
            "extracted_text_object_key IS NULL "
            "OR length(btrim(extracted_text_object_key)) BETWEEN 1 AND 512",
            name="ck_artifact_parse_result_extracted_text_object_key",
        ),
        CheckConstraint(
            "extracted_text_sha256 IS NULL "
            "OR extracted_text_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_artifact_parse_result_extracted_text_sha256",
        ),
        UniqueConstraint(
            "processing_attempt_id",
            name="uq_artifact_parse_result_processing_attempt",
        ),
        UniqueConstraint(
            "id",
            "artifact_version_id",
            name="uq_artifact_parse_result_id_version",
        ),
        ForeignKeyConstraint(
            ["processing_attempt_id", "artifact_version_id"],
            [
                "artifact_processing_attempts.id",
                "artifact_processing_attempts.artifact_version_id",
            ],
            name="fk_artifact_parse_result_attempt_same_version",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_version_id: Mapped[int] = mapped_column(
        ForeignKey("input_artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    processing_attempt_id: Mapped[int] = mapped_column(nullable=False, index=True)
    result_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text_object_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    extracted_text_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    extracted_text_char_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ArtifactProcessingJob(Base):
    """Durable queue record for one processing stage of one artifact version."""

    __tablename__ = "artifact_processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('scan', 'parse')",
            name="ck_artifact_processing_job_stage",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'rejected', 'failed')",
            name="ck_artifact_processing_job_status",
        ),
        CheckConstraint(
            "attempt_generation >= 0",
            name="ck_artifact_processing_job_attempt_generation",
        ),
        CheckConstraint(
            "retry_count >= 0 AND max_attempts > 0 AND retry_count <= max_attempts",
            name="ck_artifact_processing_job_retry_limits",
        ),
        CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_artifact_processing_job_trace_request_id",
        ),
        CheckConstraint(
            "last_error_code IS NULL OR length(btrim(last_error_code)) BETWEEN 1 AND 64",
            name="ck_artifact_processing_job_last_error_code",
        ),
        CheckConstraint(
            """
            (status = 'queued'
                AND execution_id IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NULL)
            OR (status = 'running'
                AND attempt_generation > 0
                AND execution_id IS NOT NULL
                AND lease_expires_at IS NOT NULL
                AND finished_at IS NULL)
            OR (status = 'succeeded'
                AND execution_id IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL
                AND last_error_code IS NULL)
            OR (status IN ('rejected', 'failed')
                AND execution_id IS NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL
                AND last_error_code IS NOT NULL)
            """,
            name="ck_artifact_processing_job_state_fields",
        ),
        UniqueConstraint(
            "artifact_version_id",
            "stage",
            name="uq_artifact_processing_job_version_stage",
        ),
        UniqueConstraint(
            "id", "company_id", name="uq_artifact_processing_job_id_with_company_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    artifact_version_id: Mapped[int] = mapped_column(
        ForeignKey("input_artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), server_default="queued", nullable=False, index=True
    )
    attempt_generation: Mapped[int] = mapped_column(nullable=False, server_default="0")
    retry_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(nullable=False, server_default="3")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ArtifactProcessingOutboxEvent(Base):
    """Durable publication request for one artifact-processing job."""

    __tablename__ = "artifact_processing_outbox_events"
    __table_args__ = (
        CheckConstraint(
            "event_type = 'artifact_processing_job.created'",
            name="ck_artifact_processing_outbox_event_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'published', 'publishing' )",
            name="ck_artifact_processing_outbox_status",
        ),
        CheckConstraint(
            "publish_attempt_count >= 0",
            name="ck_artifact_processing_outbox_publish_attempt_count",
        ),
        CheckConstraint(
            """
        (status = 'pending'
            AND publish_execution_id IS NULL
            AND publish_lease_expires_at IS NULL
            AND published_at IS NULL
            AND broker_message_id IS NULL)
        OR (status = 'publishing'
            AND publish_generation > 0
            AND length(btrim(publish_execution_id)) BETWEEN 1 AND 36
            AND publish_lease_expires_at IS NOT NULL
            AND published_at IS NULL
            AND broker_message_id IS NULL
            AND last_error IS NULL)
        OR (status = 'published'
            AND publish_generation > 0
            AND publish_execution_id IS NULL
            AND publish_lease_expires_at IS NULL
            AND published_at IS NOT NULL
            AND length(btrim(broker_message_id)) BETWEEN 1 AND 255
            AND last_error IS NULL)
            """,
            name="ck_artifact_processing_outbox_state_fields",
        ),
        CheckConstraint(
            "publish_generation >= 0",
            name="ck_artifact_processing_outbox_publish_generation",
        ),
        CheckConstraint(
            "dispatch_generation > 0",
            name="ck_artifact_processing_outbox_dispatch_generation",
        ),
        CheckConstraint(
            "last_error IS NULL OR length(btrim(last_error)) BETWEEN 1 AND 2000",
            name="ck_artifact_processing_outbox_last_error",
        ),
        CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_artifact_processing_outbox_trace_request_id",
        ),
        UniqueConstraint(
            "job_id",
            "dispatch_generation",
            name="uq_artifact_processing_outbox_job_dispatch_generation",
        ),
        ForeignKeyConstraint(
            ["company_id", "job_id"],
            ["artifact_processing_jobs.company_id", "artifact_processing_jobs.id"],
            name="fk_artifact_processing_outbox_event_job_company",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
    )
    broker_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), server_default="pending", nullable=False, index=True
    )
    dispatch_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )
    publish_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    publish_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    publish_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    publish_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trace_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InputArtifactUploadRequest(Base):
    __tablename__ = "input_artifact_upload_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('receiving' , 'completed' , 'rejected' , 'failed')",
            name="ck_input_artifact_upload_requests_status",
        ),
        CheckConstraint(
            """
            (status = 'receiving'
                AND payload_hash IS NULL
                AND artifact_version_id IS NULL
                AND error_code IS NULL
                AND lease_expires_at IS NOT NULL
                AND finished_at  IS NULL )
            OR (status = 'completed'
                AND payload_hash IS NOT NULL
                AND artifact_version_id  IS NOT NULL
                AND error_code IS NULL
                AND lease_expires_at IS NULL
                AND finished_at  IS NOT NULL)
            OR (status IN ('rejected','failed')
                AND  artifact_version_id  IS NULL
                AND error_code IS NOT NULL
                AND lease_expires_at IS NULL
                AND finished_at IS NOT NULL)
            """,
            name="ck_input_upload_request_state_fields",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_input_upload_request_request_fingerprint",
        ),
        CheckConstraint(
            "attempt_generation > 0",
            name="ck_input_upload_request_attempt_generation",
        ),
        CheckConstraint(
            "payload_hash IS NULL OR payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_payload_hash",
        ),
        CheckConstraint(
            "length(btrim(idempotency_key)) BETWEEN 1 AND 128",
            name="ck_input_upload_request_idempotency_key",
        ),
        CheckConstraint(
            "error_code IS NULL OR length(btrim(error_code)) BETWEEN 1 AND 64",
            name="ck_input_upload_request_error_code",
        ),
        CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_input_upload_request_trace_request_id",
        ),
        UniqueConstraint(
            "company_id",
            "submitted_by_user_id",
            "conversation_id",
            "idempotency_key",
            name="uq_input_upload_request_scope_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    submitted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_generation: Mapped[int] = mapped_column(
        nullable=False,
        server_default="1",
    )
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("input_artifact_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InputArtifactUploadSession(Base):
    """Server-owned control record for a direct-to-quarantine upload."""

    __tablename__ = "input_artifact_upload_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('awaiting_upload', 'finalizing', 'completed', 'rejected', 'expired', 'failed')",
            name="ck_input_upload_session_status",
        ),
        CheckConstraint(
            "client_reported_byte_size >= 0",
            name="ck_input_upload_session_client_reported_byte_size",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_input_upload_session_request_fingerprint",
        ),
        CheckConstraint(
            "client_reported_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_input_upload_session_client_reported_sha256",
        ),
        CheckConstraint(
            "storage_verified_sha256 IS NULL OR storage_verified_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_input_upload_session_storage_verified_sha256",
        ),
        CheckConstraint(
            "finalization_generation >= 0",
            name="ck_input_upload_session_finalization_generation",
        ),
        CheckConstraint(
            "length(btrim(idempotency_key)) BETWEEN 1 AND 128",
            name="ck_input_upload_session_idempotency_key",
        ),
        CheckConstraint(
            "length(btrim(client_filename)) BETWEEN 1 AND 255",
            name="ck_input_upload_session_client_filename",
        ),
        CheckConstraint(
            "length(btrim(staging_object_key)) BETWEEN 1 AND 512",
            name="ck_input_upload_session_staging_object_key",
        ),
        CheckConstraint(
            "length(btrim(upload_policy_version)) BETWEEN 1 AND 64",
            name="ck_input_upload_session_upload_policy_version",
        ),
        CheckConstraint(
            "failure_code IS NULL OR length(btrim(failure_code)) BETWEEN 1 AND 64",
            name="ck_input_upload_session_failure_code",
        ),
        CheckConstraint(
            "length(btrim(trace_request_id)) BETWEEN 1 AND 128",
            name="ck_input_upload_session_trace_request_id",
        ),
        CheckConstraint(
            """
            (status = 'awaiting_upload'
                AND finalization_generation = 0
                AND finalization_execution_id IS NULL
                AND finalization_lease_expires_at IS NULL
                AND storage_verified_byte_size IS NULL
                AND storage_verified_sha256 IS NULL
                AND artifact_version_id IS NULL
                AND failure_code IS NULL
                AND finished_at IS NULL)
            OR (status = 'finalizing'
                AND finalization_generation > 0
                AND finalization_execution_id IS NOT NULL
                AND finalization_lease_expires_at IS NOT NULL
                AND storage_verified_byte_size IS NULL
                AND storage_verified_sha256 IS NULL
                AND artifact_version_id IS NULL
                AND failure_code IS NULL
                AND finished_at IS NULL)
            OR (status = 'completed'
                AND finalization_generation > 0
                AND finalization_execution_id IS NULL
                AND finalization_lease_expires_at IS NULL
                AND storage_verified_byte_size IS NOT NULL
                AND storage_verified_sha256 IS NOT NULL
                AND artifact_version_id IS NOT NULL
                AND failure_code IS NULL
                AND finished_at IS NOT NULL)
            OR (status IN ('rejected', 'expired', 'failed')
                AND finalization_execution_id IS NULL
                AND finalization_lease_expires_at IS NULL
                AND storage_verified_byte_size IS NULL
                AND storage_verified_sha256 IS NULL
                AND artifact_version_id IS NULL
                AND failure_code IS NOT NULL
                AND finished_at IS NOT NULL)
            """,
            name="ck_input_upload_session_state_fields",
        ),
        UniqueConstraint("public_id", name="uq_input_upload_session_public_id"),
        UniqueConstraint(
            "company_id",
            "submitted_by_user_id",
            "conversation_id",
            "idempotency_key",
            name="uq_input_upload_session_scope_key",
        ),
        UniqueConstraint(
            "staging_object_key",
            name="uq_input_upload_session_staging_object_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36),
        default=lambda: str(uuid4()),
        nullable=False,
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    submitted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    client_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    client_reported_byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_reported_mime_type: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    client_reported_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    staging_object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_provider_upload_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="awaiting_upload",
        server_default="awaiting_upload",
        nullable=False,
        index=True,
    )
    finalization_generation: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
        nullable=False,
    )
    finalization_execution_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    finalization_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    upload_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    storage_verified_byte_size: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    storage_verified_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    artifact_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("input_artifact_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_request_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
