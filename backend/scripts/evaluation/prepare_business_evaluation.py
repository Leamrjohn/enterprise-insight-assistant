"""Prepare one disposable, auditable persisted-task evaluation scope.

This script deliberately separates deterministic preparation from the later,
paid Worker submission.  It never reads an answer key and never stores the
ephemeral API key used to create the disposable evaluation principal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.analysis.catalog.schema_discovery import discover_postgres_schema
from app.modules.conversations.models import Conversation
from app.modules.documents.models import Documents
from app.modules.evaluation.business_schemas import EvaluationCase, EvaluationFixture
from app.modules.identity.models import User
from app.modules.organizations.models import (
    BusinessDataSource,
    Company,
    CompanyMember,
    SchemaSnapshot,
)
from app.modules.workflow.lifecycle.model_budget import configured_model_budget
from app.modules.workflow.models import AnalysisTask
from scripts.evaluation.render_task_trace import load_trace, render_trace_html
from sqlalchemy import select

HARNESS_VERSION = "p0-2-persisted-baseline-v1"
DEFAULT_SOURCE_CONNECTION = {
    "host": "demo_business_acme",
    "port": 5432,
    "database": "acme_business",
    "user": "acme_readonly",
    "schema": "public",
}
DEFAULT_SOURCE_CREDENTIAL_ENV = "ACME_DEMO_DATABASE_PASSWORD"
DOCUMENT_POLL_INTERVAL_SECONDS = 1.0


class HarnessError(RuntimeError):
    """The evaluation scope cannot be safely prepared or cleaned."""


@dataclass(frozen=True)
class PreparedDocument:
    relative_path: str
    sha256: str


@dataclass(frozen=True)
class PreparationPlan:
    fixture_sha256: str
    corpus_manifest_sha256: str
    dataset_version: str
    corpus_version: str
    corpus_seed: int
    cases: tuple[EvaluationCase, ...]
    documents: tuple[PreparedDocument, ...]


@dataclass(frozen=True)
class PreparedScope:
    manifest_path: Path
    api_key: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_fixture(path: Path) -> EvaluationFixture:
    try:
        return EvaluationFixture.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HarnessError(f"cannot read evaluation fixture: {path}") from exc


def _select_cases(
    fixture: EvaluationFixture,
    requested_case_ids: list[str] | None,
    *,
    heldout_evaluation: bool = False,
) -> tuple[EvaluationCase, ...]:
    selected = tuple(
        case
        for case in fixture.cases
        if requested_case_ids is None or case.case_id in set(requested_case_ids)
    )
    if not selected:
        raise HarnessError("at least one known --case-id is required")
    selected_ids = {case.case_id for case in selected}
    requested_ids = set(requested_case_ids or selected_ids)
    unknown = sorted(requested_ids - {case.case_id for case in fixture.cases})
    if unknown:
        raise HarnessError(f"unknown evaluation case IDs: {unknown}")
    if requested_case_ids is not None and len(requested_case_ids) != len(requested_ids):
        raise HarnessError("--case-id values must not contain duplicates")
    heldout = sorted(case.case_id for case in selected if case.split == "heldout")
    if heldout and not heldout_evaluation:
        raise HarnessError(
            f"heldout cases are frozen and cannot enter preparation: {heldout}"
        )
    if heldout_evaluation and (not heldout or len(heldout) != len(selected)):
        raise HarnessError(
            "heldout evaluation requires explicitly selected heldout cases only"
        )
    security_cases = sorted(
        case.case_id
        for case in selected
        if case.evaluation_kind == "security_rejection"
    )
    if security_cases:
        raise HarnessError(
            "request-rejection cases require an independently verified HTTP rejection "
            "route and cannot be submitted as analysis tasks: "
            f"{security_cases}"
        )
    probe_cases = sorted(
        case.case_id
        for case in selected
        if case.evaluation_kind not in {"analysis", "clarification"}
    )
    if probe_cases:
        raise HarnessError(
            "non-task cases require a dedicated evaluation executor and cannot "
            f"be submitted as analysis tasks: {probe_cases}"
        )
    return selected


def build_preparation_plan(
    *,
    fixture_path: Path,
    corpus_dir: Path,
    requested_case_ids: list[str] | None,
    heldout_evaluation: bool = False,
) -> PreparationPlan:
    fixture = _read_fixture(fixture_path)
    cases = _select_cases(
        fixture,
        requested_case_ids,
        heldout_evaluation=heldout_evaluation,
    )
    manifest_path = corpus_dir / "manifest.json"
    try:
        corpus_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read corpus manifest: {manifest_path}") from exc
    artifacts = corpus_manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise HarnessError("corpus manifest artifacts must be a list")
    known_hashes = {
        item.get("path"): item.get("sha256")
        for item in artifacts
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("sha256"), str)
    }
    requested_paths = sorted(
        {
            document_path
            for case in cases
            for document_path in (case.document_scope or [])
        }
    )
    documents: list[PreparedDocument] = []
    for relative_path in requested_paths:
        expected_sha256 = known_hashes.get(relative_path)
        document_path = corpus_dir / relative_path
        if expected_sha256 is None or not document_path.is_file():
            raise HarnessError(
                f"case document is absent from the frozen corpus: {relative_path}"
            )
        actual_sha256 = _sha256_file(document_path)
        if actual_sha256 != expected_sha256:
            raise HarnessError(
                f"case document hash differs from corpus manifest: {relative_path}"
            )
        documents.append(PreparedDocument(relative_path, actual_sha256))
    version = corpus_manifest.get("version")
    seed = corpus_manifest.get("seed")
    if not isinstance(version, str) or not isinstance(seed, int):
        raise HarnessError("corpus manifest version and seed are required")
    return PreparationPlan(
        fixture_sha256=_sha256_file(fixture_path),
        corpus_manifest_sha256=_sha256_file(manifest_path),
        dataset_version=fixture.dataset_version,
        corpus_version=version,
        corpus_seed=seed,
        cases=cases,
        documents=tuple(documents),
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _require_new_output_dir(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise HarnessError(f"output directory must be new or empty: {output_dir}")


def _validate_platform_database_name(*, actual: str, expected: str) -> None:
    if not expected.strip():
        raise HarnessError("expected platform database name must not be blank")
    if actual != expected:
        raise HarnessError(
            "preparation database does not match the API database: "
            f"actual={actual!r}, expected={expected!r}"
        )


def _require_platform_database(expected_name: str) -> None:
    _validate_platform_database_name(
        actual=get_settings().database_name,
        expected=expected_name,
    )


def _validate_submission_budget(
    *, default_task_max_cost: str, requested_cost_ceiling: str
) -> None:
    try:
        task_cap = Decimal(default_task_max_cost)
        requested_cap = Decimal(requested_cost_ceiling)
    except (InvalidOperation, TypeError) as exc:
        raise HarnessError("model cost limits must be decimal values") from exc
    if not task_cap.is_finite() or not requested_cap.is_finite():
        raise HarnessError("model cost limits must be finite")
    if task_cap <= 0 or requested_cap <= 0:
        raise HarnessError("model cost limits must be positive")
    if task_cap > requested_cap:
        raise HarnessError(
            "current task model budget exceeds the requested evaluation ceiling: "
            f"task={task_cap}, requested={requested_cap}"
        )


def _require_submission_governance(requested_cost_ceiling: str) -> None:
    default_budget = configured_model_budget(get_settings())
    default_task_max_cost = default_budget.get("max_cost")
    if not isinstance(default_task_max_cost, str):
        raise HarnessError("default task model budget has no decimal max_cost")
    _validate_submission_budget(
        default_task_max_cost=default_task_max_cost,
        requested_cost_ceiling=requested_cost_ceiling,
    )
    settings = get_settings()
    if (
        settings.model_price_table_version == "unconfigured"
        or not settings.model_price_table
    ):
        raise HarnessError(
            "provider price table is unconfigured; paid evaluation submission is blocked"
        )


def _bootstrap_tenant(run_id: str) -> tuple[dict[str, int], str]:
    """Create the disposable tenant before any externally fallible operation."""
    api_key = secrets.token_urlsafe(32)
    db = SessionLocal()
    try:
        user = User(name=f"p0-evaluation-{run_id}", api_key=api_key)
        company = Company(name=f"p0-evaluation-{run_id}")
        db.add_all((user, company))
        db.flush()
        membership = CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role="owner",
            status="approved",
        )
        db.add(membership)
        db.commit()
        return (
            {
                "user_id": user.id,
                "company_id": company.id,
                "membership_id": membership.id,
            },
            api_key,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _create_source_snapshot(
    resource_ids: dict[str, int], run_id: str
) -> dict[str, int]:
    """Discover the real read-only schema after cleanup IDs are persisted."""
    company_id = resource_ids["company_id"]
    user_id = resource_ids["user_id"]
    db = SessionLocal()
    try:
        set_tenant_scope(db, company_id)
        source = BusinessDataSource(
            company_id=company_id,
            name=f"p0-evaluation-{run_id}-acme-readonly",
            dialect="postgresql",
            connection_config=DEFAULT_SOURCE_CONNECTION,
            credential_env_var=DEFAULT_SOURCE_CREDENTIAL_ENV,
            status="pending",
        )
        db.add(source)
        db.flush()
        catalog, fingerprint = discover_postgres_schema(source)
        snapshot = SchemaSnapshot(
            data_source_id=source.id,
            catalog=catalog,
            fingerprint=fingerprint,
            discovered_by_user_id=user_id,
        )
        db.add(snapshot)
        db.flush()
        source.active_schema_snapshot_id = snapshot.id
        source.status = "ready"
        source.last_error = None
        db.commit()
        return {"data_source_id": source.id, "schema_snapshot_id": snapshot.id}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _api_client(api_url: str, api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=api_url.rstrip("/") + "/",
        headers={"X-API-Key": api_key},
        timeout=httpx.Timeout(10.0),
        follow_redirects=False,
    )


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    expected_status: int,
    payload: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    headers = {"X-Request-ID": request_id} if request_id else None
    response = client.request(method, path, json=payload, headers=headers)
    if response.status_code != expected_status:
        raise HarnessError(
            f"API {method} {path} returned {response.status_code}, expected {expected_status}"
        )
    try:
        result = response.json()
    except json.JSONDecodeError as exc:
        raise HarnessError(f"API {method} {path} returned non-JSON") from exc
    if not isinstance(result, dict):
        raise HarnessError(f"API {method} {path} returned a non-object JSON payload")
    return result


def _wait_for_document(
    client: httpx.Client, *, document_id: int, timeout_seconds: int
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        document = _request_json(
            client, "GET", f"documents/{document_id}", expected_status=200
        )
        status = document.get("status")
        if status == "completed":
            return
        if status == "failed":
            raise HarnessError(f"document worker failed for document {document_id}")
        if time.monotonic() >= deadline:
            raise HarnessError(
                f"document worker timed out after {timeout_seconds}s for document {document_id}"
            )
        # The API limit is 100 requests per key per rolling minute. A 0.5-second
        # poll would exhaust that limit before this harness's 90-second timeout.
        time.sleep(DOCUMENT_POLL_INTERVAL_SECONDS)


def _upload_documents(
    *,
    client: httpx.Client,
    plan: PreparationPlan,
    corpus_dir: Path,
    run_id: str,
    timeout_seconds: int,
    on_document_created: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    uploaded: list[dict[str, Any]] = []
    for document in plan.documents:
        content = (corpus_dir / document.relative_path).read_text(encoding="utf-8")
        record = _request_json(
            client,
            "POST",
            "documents",
            expected_status=202,
            request_id=f"p0-{run_id}-doc-{len(uploaded)}",
            payload={
                "name": document.relative_path,
                "content": content,
                "source": document.relative_path,
                "min_view_role": "any",
            },
        )
        document_id = record.get("id")
        if isinstance(document_id, bool) or not isinstance(document_id, int):
            raise HarnessError("document create response did not include an integer ID")
        uploaded_document = {
            "document_id": document_id,
            "path": document.relative_path,
            "sha256": document.sha256,
        }
        uploaded.append(uploaded_document)
        if on_document_created is not None:
            on_document_created(uploaded_document)
        _wait_for_document(
            client, document_id=document_id, timeout_seconds=timeout_seconds
        )
    return uploaded


def _assert_no_answer_key_in_plan(plan: PreparationPlan) -> None:
    serialized = json.dumps(
        {
            "cases": [
                {
                    "case_id": case.case_id,
                    "question": case.question,
                    "document_scope": case.document_scope,
                }
                for case in plan.cases
            ]
        },
        ensure_ascii=False,
    )
    forbidden_markers = ("expected_result_fingerprint", "expected_supported_claims")
    if any(marker in serialized for marker in forbidden_markers):
        raise HarnessError("evaluation answer fields entered the preparation payload")


def prepare(
    *,
    fixture_path: Path,
    corpus_dir: Path,
    output_dir: Path,
    api_url: str,
    requested_case_ids: list[str] | None,
    heldout_evaluation: bool,
    document_timeout_seconds: int,
    platform_database_name: str,
) -> PreparedScope:
    _require_platform_database(platform_database_name)
    _require_new_output_dir(output_dir)
    plan = build_preparation_plan(
        fixture_path=fixture_path,
        corpus_dir=corpus_dir,
        requested_case_ids=requested_case_ids,
        heldout_evaluation=heldout_evaluation,
    )
    _assert_no_answer_key_in_plan(plan)
    run_id = f"p0-{uuid4().hex}"
    manifest_path = output_dir / "prepare.json"
    manifest: dict[str, Any] = {
        "harness_version": HARNESS_VERSION,
        "state": "planning",
        "run_id": run_id,
        "fixture": {
            "dataset_version": plan.dataset_version,
            "sha256": plan.fixture_sha256,
        },
        "corpus": {
            "version": plan.corpus_version,
            "seed": plan.corpus_seed,
            "manifest_sha256": plan.corpus_manifest_sha256,
        },
        "api_url": api_url,
        "case_ids": [case.case_id for case in plan.cases],
        "heldout_evaluation": heldout_evaluation,
        "cases": [
            {
                "case_id": case.case_id,
                "question": case.question,
                "document_scope": case.document_scope or [],
                "max_model_calls": case.max_model_calls,
                "max_tokens": case.max_tokens,
            }
            for case in plan.cases
        ],
        "documents": [],
        "task_map": {},
        "rejection_map": {},
        "cleanup": {"state": "pending", "resource_ids": {}},
    }
    _write_json(manifest_path, manifest)
    resource_ids, api_key = _bootstrap_tenant(run_id)
    manifest["cleanup"]["resource_ids"] = resource_ids
    manifest["api_key_sha256"] = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    manifest["state"] = "bootstrapped"
    _write_json(manifest_path, manifest)
    try:
        resource_ids.update(_create_source_snapshot(resource_ids, run_id))
        _write_json(manifest_path, manifest)
        with _api_client(api_url, api_key) as client:
            _upload_documents(
                client=client,
                plan=plan,
                corpus_dir=corpus_dir,
                run_id=run_id,
                timeout_seconds=document_timeout_seconds,
                on_document_created=lambda document: (
                    manifest["documents"].append(document),
                    _write_json(manifest_path, manifest),
                ),
            )
        manifest["state"] = "prepared"
        _write_json(manifest_path, manifest)
    except Exception:
        manifest["state"] = "prepare_failed_cleanup_required"
        _write_json(manifest_path, manifest)
        raise
    return PreparedScope(manifest_path=manifest_path, api_key=api_key)


def _load_prepared_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(
            f"cannot read preparation manifest: {manifest_path}"
        ) from exc
    if manifest.get("harness_version") != HARNESS_VERSION:
        raise HarnessError("preparation manifest has an unknown harness version")
    if manifest.get("state") != "prepared":
        raise HarnessError("only a fully prepared manifest may submit analysis tasks")
    return manifest


def _existing_task_id(*, request_id: str, company_id: int) -> int | None:
    with SessionLocal() as db:
        set_tenant_scope(db, company_id)
        task_ids = db.scalars(
            select(AnalysisTask.id).where(
                AnalysisTask.request_id == request_id,
                AnalysisTask.company_id == company_id,
            )
        ).all()
    if len(task_ids) > 1:
        raise HarnessError(f"request ID maps to multiple tasks: {request_id}")
    return task_ids[0] if task_ids else None


def submit_prepared_tasks(
    *,
    prepared_scope: PreparedScope,
    max_submissions: int,
    requested_cost_ceiling: str,
) -> Path:
    if max_submissions <= 0:
        raise HarnessError("max submissions must be positive")
    _require_submission_governance(requested_cost_ceiling)
    manifest = _load_prepared_manifest(prepared_scope.manifest_path)
    cases = manifest.get("cases")
    documents = manifest.get("documents")
    resource_ids = manifest.get("cleanup", {}).get("resource_ids")
    if (
        not isinstance(cases, list)
        or not isinstance(documents, list)
        or not isinstance(resource_ids, dict)
    ):
        raise HarnessError("prepared manifest has invalid task-submission fields")
    if len(cases) > max_submissions:
        raise HarnessError(
            f"prepared scope has {len(cases)} cases, above max submissions {max_submissions}"
        )
    company_id = resource_ids.get("company_id")
    data_source_id = resource_ids.get("data_source_id")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (company_id, data_source_id)
    ):
        raise HarnessError("prepared manifest has invalid company or source ID")
    document_ids_by_path = {
        item.get("path"): item.get("document_id")
        for item in documents
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("document_id"), int)
    }
    task_map = manifest.get("task_map")
    if not isinstance(task_map, dict):
        raise HarnessError("prepared manifest task map must be an object")
    run_id = manifest.get("run_id")
    api_url = manifest.get("api_url")
    if not isinstance(run_id, str) or not isinstance(api_url, str):
        raise HarnessError("prepared manifest has invalid run metadata")
    with _api_client(api_url, prepared_scope.api_key) as client:
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                raise HarnessError("prepared manifest case must be an object")
            case_id = case.get("case_id")
            question = case.get("question")
            document_scope = case.get("document_scope")
            if (
                not isinstance(case_id, str)
                or not isinstance(question, str)
                or not isinstance(document_scope, list)
                or not all(isinstance(path, str) for path in document_scope)
            ):
                raise HarnessError(
                    "prepared manifest case has invalid submission fields"
                )
            if case_id in task_map:
                continue
            request_id = f"{run_id}-task-{index}"
            task_id = _existing_task_id(request_id=request_id, company_id=company_id)
            if task_id is None:
                document_ids = [
                    document_ids_by_path.get(path) for path in document_scope
                ]
                if any(
                    isinstance(document_id, bool) or not isinstance(document_id, int)
                    for document_id in document_ids
                ):
                    raise HarnessError(
                        f"prepared manifest has no document ID for case {case_id}"
                    )
                conversation = _request_json(
                    client,
                    "POST",
                    "conversations",
                    expected_status=201,
                    payload={
                        "title": f"P0 evaluation {case_id}",
                        "data_source_id": data_source_id,
                    },
                )
                conversation_id = conversation.get("id")
                if isinstance(conversation_id, bool) or not isinstance(
                    conversation_id, int
                ):
                    raise HarnessError(
                        "conversation create response did not include an integer ID"
                    )
                accepted = _request_json(
                    client,
                    "POST",
                    f"conversations/{conversation_id}/messages",
                    expected_status=202,
                    request_id=request_id,
                    payload={"content": question, "document_ids": document_ids},
                )
                task_id = accepted.get("task_id")
                if isinstance(task_id, bool) or not isinstance(task_id, int):
                    raise HarnessError(
                        "analysis submission did not return an integer task ID"
                    )
            task_map[case_id] = task_id
            _write_json(prepared_scope.manifest_path, manifest)
    manifest["state"] = "submitted"
    _write_json(prepared_scope.manifest_path, manifest)
    return prepared_scope.manifest_path


def cleanup(*, manifest_path: Path) -> None:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(
            f"cannot read preparation manifest: {manifest_path}"
        ) from exc
    if manifest.get("harness_version") != HARNESS_VERSION:
        raise HarnessError("preparation manifest has an unknown harness version")
    resource_ids = manifest.get("cleanup", {}).get("resource_ids")
    if not isinstance(resource_ids, dict):
        raise HarnessError("preparation manifest has no cleanup resource IDs")
    company_id = resource_ids.get("company_id")
    user_id = resource_ids.get("user_id")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (company_id, user_id)
    ):
        raise HarnessError("cleanup resource IDs are invalid")
    task_ids = [
        task_id
        for task_id in (manifest.get("task_map") or {}).values()
        if isinstance(task_id, int)
    ]
    db = SessionLocal()
    try:
        set_tenant_scope(db, company_id)
        live_tasks = (
            db.scalars(
                select(AnalysisTask).where(
                    AnalysisTask.id.in_(task_ids), AnalysisTask.company_id == company_id
                )
            ).all()
            if task_ids
            else []
        )
        non_terminal = [
            task.id
            for task in live_tasks
            if task.status in {"queued", "running", "retrying"}
        ]
        if non_terminal:
            raise HarnessError(
                f"refusing cleanup while tasks are non-terminal: {non_terminal}"
            )
        trace_dir = manifest_path.parent / "traces"
        trace_paths: dict[str, str] = {}
        for task in live_tasks:
            trace_task, attempts, events, model_calls, tool_calls = load_trace(
                db, company_id=company_id, task_id=task.id
            )
            trace_path = trace_dir / f"task-{task.id}.html"
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                render_trace_html(
                    task=trace_task,
                    attempts=attempts,
                    events=events,
                    model_calls=model_calls,
                    tool_calls=tool_calls,
                ),
                encoding="utf-8",
            )
            trace_paths[str(task.id)] = str(trace_path)
        manifest["cleanup"]["trace_paths"] = trace_paths
        _write_json(manifest_path, manifest)
        for task in live_tasks:
            db.delete(task)
        db.flush()
        for document in db.scalars(
            select(Documents).where(Documents.company_id == company_id)
        ).all():
            db.delete(document)
        db.flush()
        snapshot_id = resource_ids.get("schema_snapshot_id")
        if isinstance(snapshot_id, int):
            snapshot = db.get(SchemaSnapshot, snapshot_id)
            if snapshot is not None and snapshot.data_source_id == resource_ids.get(
                "data_source_id"
            ):
                db.delete(snapshot)
        db.flush()
        for conversation in db.scalars(
            select(Conversation).where(Conversation.company_id == company_id)
        ).all():
            db.delete(conversation)
        db.flush()
        source_id = resource_ids.get("data_source_id")
        if isinstance(source_id, int):
            source = db.get(BusinessDataSource, source_id)
            if source is not None and source.company_id == company_id:
                db.delete(source)
        db.flush()
        company = db.get(Company, company_id)
        if company is not None:
            db.delete(company)
        db.flush()
        user = db.get(User, user_id)
        if user is not None:
            db.delete(user)
        db.commit()
        manifest["cleanup"]["state"] = "completed"
        _write_json(manifest_path, manifest)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--fixture", type=Path, required=True)
    prepare_parser.add_argument("--corpus-dir", type=Path, required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--api-url", required=True)
    prepare_parser.add_argument("--platform-database-name", required=True)
    prepare_parser.add_argument("--case-id", action="append", dest="case_ids")
    prepare_parser.add_argument("--heldout-evaluation", action="store_true")
    prepare_parser.add_argument("--document-timeout-seconds", type=int, default=120)
    prepare_parser.add_argument("--submit-analysis-tasks", action="store_true")
    prepare_parser.add_argument("--max-submissions", type=int, default=1)
    prepare_parser.add_argument("--max-cost-usd")
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        if args.document_timeout_seconds <= 0:
            parser.error("--document-timeout-seconds must be positive")
        if args.submit_analysis_tasks:
            if args.max_cost_usd is None:
                parser.error("--submit-analysis-tasks requires --max-cost-usd")
            _require_submission_governance(args.max_cost_usd)
        prepared_scope = prepare(
            fixture_path=args.fixture,
            corpus_dir=args.corpus_dir,
            output_dir=args.output_dir,
            api_url=args.api_url,
            requested_case_ids=args.case_ids,
            heldout_evaluation=args.heldout_evaluation,
            document_timeout_seconds=args.document_timeout_seconds,
            platform_database_name=args.platform_database_name,
        )
        if args.submit_analysis_tasks:
            submit_prepared_tasks(
                prepared_scope=prepared_scope,
                max_submissions=args.max_submissions,
                requested_cost_ceiling=args.max_cost_usd,
            )
        print(prepared_scope.manifest_path)
    else:
        cleanup(manifest_path=args.manifest)
        print(args.manifest)


if __name__ == "__main__":
    main()
