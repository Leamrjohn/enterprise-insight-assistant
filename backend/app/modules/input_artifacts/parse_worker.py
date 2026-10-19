"""One claimed parse-job execution, independent of the Celery transport."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from collections.abc import Callable

from app.modules.input_artifacts.models import InputArtifactVersion
from app.modules.input_artifacts.parser import (
    ImageParseLimits,
    InputArtifactParseError,
    PdfParseLimits,
    parse_input_artifact_file,
)
from app.modules.input_artifacts.processing_jobs import (
    claim_parse_job_for_processing,
    complete_parse_job_processing,
    fail_parse_job_processing,
)
from app.modules.input_artifacts.processing_storage import (
    ArtifactProcessingObjectNotFoundError,
    ArtifactProcessingStorage,
    ArtifactProcessingStorageUnavailableError,
)
from sqlalchemy.orm import Session


def execute_parse_job(
    db: Session,
    *,
    job_id: int,
    dispatch_generation: int,
    processor_name: str,
    processor_version: str,
    storage_factory: Callable[[], ArtifactProcessingStorage],
    image_limits: ImageParseLimits = ImageParseLimits(),
    pdf_limits: PdfParseLimits = PdfParseLimits(),
    image_ocr: Callable[[Path], object] | None = None,
    pdf_page_renderer: Callable[[Path, int, Path], Path] | None = None,
) -> bool:
    """Claim, parse, persist immutable output, and complete one parse job."""
    claim = claim_parse_job_for_processing(
        db,
        job_id=job_id,
        expected_dispatch_generation=dispatch_generation,
        processor_name=processor_name,
        processor_version=processor_version,
    )
    if claim is None:
        return False
    try:
        storage = storage_factory()
    except Exception:
        return _fail(db, claim, "processor_configuration_unavailable")
    version = db.get(InputArtifactVersion, claim.artifact_version_id)
    if version is None:
        raise RuntimeError("claimed parse job version is not visible")

    try:
        with TemporaryDirectory(prefix="artifact-parse-") as temporary_directory:
            temporary_path = Path(temporary_directory)
            raw_path = temporary_path / "raw-input"
            downloaded = storage.download_quarantine_object(
                object_key=version.raw_object_key,
                destination_path=raw_path,
            )
            if (
                downloaded.byte_size != version.byte_size
                or downloaded.sha256_hex != version.sha256
            ):
                return _fail(db, claim, "object_integrity_mismatch")
            parsed = parse_input_artifact_file(
                source_path=raw_path,
                original_filename=version.original_filename,
                output_directory=temporary_path / "parsed",
                image_limits=image_limits,
                pdf_limits=pdf_limits,
                image_ocr=image_ocr,
                pdf_page_renderer=pdf_page_renderer,
            )
            result_prefix = (
                f"input-artifacts/parsed/{claim.company_id}/"
                f"{claim.artifact_version_id}/attempt-{claim.generation}"
            )
            manifest_content = json.dumps(
                {**parsed.manifest, "source_sha256": version.sha256},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            manifest = storage.write_parsed_object(
                object_key=f"{result_prefix}/manifest.json",
                content=manifest_content,
                content_type="application/json",
            )
            extracted_text = storage.write_parsed_file(
                object_key=f"{result_prefix}/extracted.txt",
                source_path=parsed.extracted_text_path,
                content_type="text/plain; charset=utf-8",
            )
    except ArtifactProcessingObjectNotFoundError:
        return _fail(db, claim, "quarantine_object_missing")
    except ArtifactProcessingStorageUnavailableError:
        return _fail(db, claim, "parse_storage_unavailable")
    except InputArtifactParseError as exc:
        return _fail(db, claim, exc.error_code)

    return complete_parse_job_processing(
        db,
        job_id=claim.job_id,
        execution_id=claim.execution_id,
        expected_generation=claim.generation,
        result_schema_version=str(parsed.manifest["schema_version"]),
        manifest_object_key=manifest.object_key,
        manifest_sha256=manifest.sha256_hex,
        extracted_text_object_key=extracted_text.object_key,
        extracted_text_sha256=extracted_text.sha256_hex,
        extracted_text_char_count=parsed.extracted_text_char_count,
    )


def _fail(db: Session, claim, error_code: str) -> bool:
    return fail_parse_job_processing(
        db,
        job_id=claim.job_id,
        execution_id=claim.execution_id,
        expected_generation=claim.generation,
        error_code=error_code,
    )
