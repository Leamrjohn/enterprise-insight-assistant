import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import scripts.evaluation.prepare_business_evaluation as evaluation_harness
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.documents.models import Documents
from app.modules.identity.models import User
from app.modules.organizations.models import (
    BusinessDataSource,
    Company,
    CompanyMember,
    SchemaSnapshot,
)
from app.modules.workflow.models import AnalysisTask
from scripts.evaluation.prepare_business_evaluation import (
    DEFAULT_SOURCE_CONNECTION,
    DEFAULT_SOURCE_CREDENTIAL_ENV,
    HarnessError,
    _require_submission_governance,
    _validate_platform_database_name,
    _validate_submission_budget,
    build_preparation_plan,
    cleanup,
)


def _case(*, case_id: str = "analysis-case", **overrides) -> dict:
    case = {
        "case_id": case_id,
        "scenario": "sales_decline",
        "complexity": "medium",
        "split": "development",
        "coverage_tags": ["planner"],
        "question": "华东销售为何下降？",
        "company_scope": "acme-demo",
        "document_scope": ["events/east.md"],
        "expected_route": "hybrid",
        "expected_entities": ["华东"],
        "expected_period": "2025-08",
        "expected_query_requirements": ["查询销售额"],
        "expected_result_fingerprint": {"scenario": "sales_decline"},
        "expected_outcome": "partial",
        "max_model_calls": 4,
        "max_tokens": 8000,
    }
    case.update(overrides)
    return case


def _write_fixture_and_corpus(tmp_path: Path, case: dict) -> tuple[Path, Path]:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps({"dataset_version": "gold-v1", "cases": [case]}),
        encoding="utf-8",
    )
    corpus_dir = tmp_path / "corpus"
    document_path = corpus_dir / "events" / "east.md"
    document_path.parent.mkdir(parents=True)
    document_path.write_text("已授权业务资料", encoding="utf-8")
    document_sha256 = hashlib.sha256(document_path.read_bytes()).hexdigest()
    (corpus_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "seed": 20260718,
                "artifacts": [{"path": "events/east.md", "sha256": document_sha256}],
            }
        ),
        encoding="utf-8",
    )
    return fixture_path, corpus_dir


def test_default_source_matches_the_compose_managed_acme_readonly_contract() -> None:
    assert DEFAULT_SOURCE_CONNECTION == {
        "host": "demo_business_acme",
        "port": 5432,
        "database": "acme_business",
        "user": "acme_readonly",
        "schema": "public",
    }
    assert DEFAULT_SOURCE_CREDENTIAL_ENV == "ACME_DEMO_DATABASE_PASSWORD"


def test_database_validation_refuses_a_test_container_for_live_api_work() -> None:
    with pytest.raises(HarnessError, match="does not match"):
        _validate_platform_database_name(
            actual="agent_platform_test", expected="agent_platform"
        )


def test_submission_budget_refuses_a_task_cap_above_the_user_ceiling() -> None:
    with pytest.raises(HarnessError, match="exceeds"):
        _validate_submission_budget(
            default_task_max_cost="1.00", requested_cost_ceiling="0.15"
        )

    _validate_submission_budget(
        default_task_max_cost="0.15", requested_cost_ceiling="0.15"
    )


@pytest.mark.parametrize("invalid", ["NaN", "sNaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["default_task_max_cost", "requested_cost_ceiling"])
def test_submission_budget_rejects_nonfinite_limits(field: str, invalid: str) -> None:
    limits = {"default_task_max_cost": "0.15", "requested_cost_ceiling": "0.15"}
    limits[field] = invalid
    with pytest.raises(HarnessError, match="finite"):
        _validate_submission_budget(**limits)


def test_submission_governance_uses_the_server_owned_task_budget(monkeypatch) -> None:
    settings = get_settings().model_copy(
        update={"analysis_task_model_max_cost": "0.16"}
    )
    monkeypatch.setattr(evaluation_harness, "get_settings", lambda: settings)

    with pytest.raises(HarnessError, match="exceeds"):
        _require_submission_governance("0.15")


def test_plan_freezes_only_requested_document_metadata(tmp_path: Path) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(tmp_path, _case())

    plan = build_preparation_plan(
        fixture_path=fixture_path,
        corpus_dir=corpus_dir,
        requested_case_ids=["analysis-case"],
    )

    assert plan.dataset_version == "gold-v1"
    assert [document.relative_path for document in plan.documents] == ["events/east.md"]
    assert (
        plan.documents[0].sha256
        == hashlib.sha256((corpus_dir / "events" / "east.md").read_bytes()).hexdigest()
    )


def test_plan_selects_all_fixture_cases_when_case_id_is_omitted(tmp_path: Path) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(tmp_path, _case())

    plan = build_preparation_plan(
        fixture_path=fixture_path,
        corpus_dir=corpus_dir,
        requested_case_ids=None,
    )

    assert [case.case_id for case in plan.cases] == ["analysis-case"]


def test_plan_refuses_a_hash_mismatch_in_the_frozen_corpus(tmp_path: Path) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(tmp_path, _case())
    (corpus_dir / "events" / "east.md").write_text("篡改后资料", encoding="utf-8")

    with pytest.raises(HarnessError, match="hash differs"):
        build_preparation_plan(
            fixture_path=fixture_path,
            corpus_dir=corpus_dir,
            requested_case_ids=["analysis-case"],
        )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        (_case(split="heldout"), "heldout cases"),
        (
            _case(evaluation_kind="security_rejection", expected_route=None),
            "request-rejection cases",
        ),
    ],
)
def test_plan_refuses_cases_without_a_valid_preparation_route(
    tmp_path: Path, case: dict, message: str
) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(tmp_path, case)

    with pytest.raises(HarnessError, match=message):
        build_preparation_plan(
            fixture_path=fixture_path,
            corpus_dir=corpus_dir,
            requested_case_ids=["analysis-case"],
        )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "business_runtime_tool_rejection_development_v1.json",
        "business_sql_schema_injection_rejection_development_v1.json",
        "business_sql_timeout_development_v1.json",
        "business_sql_result_limit_development_v1.json",
        "business_duplicate_delivery_rejection_development_v1.json",
        "business_execution_fence_cancellation_development_v1.json",
    ],
)
def test_plan_rejects_dedicated_probes_before_reading_corpus(
    tmp_path: Path, fixture_name: str
) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1] / "fixtures/evaluation" / fixture_name
    )
    with pytest.raises(HarnessError, match="dedicated evaluation executor"):
        build_preparation_plan(
            fixture_path=fixture_path,
            corpus_dir=tmp_path / "must-not-be-read",
            requested_case_ids=None,
        )


def test_plan_allows_a_development_clarification_case(tmp_path: Path) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(
        tmp_path,
        _case(
            evaluation_kind="clarification",
            document_scope=[],
            expected_route=None,
            expected_outcome="needs_clarification",
            expected_clarification_missing_fields=["time_range"],
        ),
    )

    plan = build_preparation_plan(
        fixture_path=fixture_path,
        corpus_dir=corpus_dir,
        requested_case_ids=["analysis-case"],
    )

    assert [case.evaluation_kind for case in plan.cases] == ["clarification"]
    assert plan.documents == ()


def test_plan_allows_only_explicit_heldout_evaluation(tmp_path: Path) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(
        tmp_path,
        _case(split="heldout", document_scope=[]),
    )

    plan = build_preparation_plan(
        fixture_path=fixture_path,
        corpus_dir=corpus_dir,
        requested_case_ids=["analysis-case"],
        heldout_evaluation=True,
    )

    assert [case.case_id for case in plan.cases] == ["analysis-case"]
    assert plan.documents == ()

    fixture_path.write_text(
        json.dumps(
            {
                "dataset_version": "gold-v1",
                "cases": [
                    _case(split="heldout", document_scope=[]),
                    _case(
                        case_id="development-case",
                        split="development",
                        document_scope=[],
                    ),
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HarnessError, match="heldout cases only"):
        build_preparation_plan(
            fixture_path=fixture_path,
            corpus_dir=corpus_dir,
            requested_case_ids=["analysis-case", "development-case"],
            heldout_evaluation=True,
        )


def test_document_preparation_uses_json_without_answer_keys(tmp_path: Path) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(
        tmp_path,
        _case(expected_supported_claims=["answer-key-must-not-be-sent"]),
    )
    plan = build_preparation_plan(
        fixture_path=fixture_path,
        corpus_dir=corpus_dir,
        requested_case_ids=["analysis-case"],
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/documents"
            assert request.headers["content-type"] == "application/json"
            assert request.headers["x-request-id"] == "p0-contract-doc-0"
            assert json.loads(request.content) == {
                "name": "events/east.md",
                "content": "已授权业务资料",
                "source": "events/east.md",
                "min_view_role": "any",
            }
            return httpx.Response(202, json={"id": 73})
        assert request.method == "GET"
        assert request.url.path == "/documents/73"
        return httpx.Response(200, json={"status": "completed"})

    with httpx.Client(
        base_url="http://evaluation.test/", transport=httpx.MockTransport(respond)
    ) as client:
        documents = evaluation_harness._upload_documents(
            client=client,
            plan=plan,
            corpus_dir=corpus_dir,
            run_id="contract",
            timeout_seconds=1,
        )

    assert len(requests) == 2
    assert documents == [
        {
            "document_id": 73,
            "path": "events/east.md",
            "sha256": plan.documents[0].sha256,
        }
    ]


def test_upload_records_document_id_before_wait_failure(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_path, corpus_dir = _write_fixture_and_corpus(tmp_path, _case())
    plan = build_preparation_plan(
        fixture_path=fixture_path,
        corpus_dir=corpus_dir,
        requested_case_ids=["analysis-case"],
    )
    persisted: list[dict] = []
    monkeypatch.setattr(
        evaluation_harness,
        "_request_json",
        lambda *args, **kwargs: {"id": 73},
    )
    monkeypatch.setattr(
        evaluation_harness,
        "_wait_for_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(HarnessError("timed out")),
    )

    with pytest.raises(HarnessError, match="timed out"):
        evaluation_harness._upload_documents(
            client=object(),
            plan=plan,
            corpus_dir=corpus_dir,
            run_id="p0-test",
            timeout_seconds=1,
            on_document_created=persisted.append,
        )

    assert persisted == [
        {
            "document_id": 73,
            "path": "events/east.md",
            "sha256": plan.documents[0].sha256,
        }
    ]


def test_document_poll_interval_stays_below_the_api_key_rate_limit(
    monkeypatch,
) -> None:
    responses = iter(({"status": "processing"}, {"status": "completed"}))
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        evaluation_harness,
        "_request_json",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr(
        evaluation_harness.time,
        "sleep",
        sleep_calls.append,
    )

    evaluation_harness._wait_for_document(
        client=object(), document_id=73, timeout_seconds=90
    )

    assert sleep_calls == [evaluation_harness.DOCUMENT_POLL_INTERVAL_SECONDS]
    assert evaluation_harness.DOCUMENT_POLL_INTERVAL_SECONDS >= 1.0


def test_cleanup_deletes_a_discovered_snapshot_before_its_user(
    migrated_test_database: None, tmp_path: Path
) -> None:
    db = SessionLocal()
    user_id: int | None = None
    company_id: int | None = None
    source_id: int | None = None
    snapshot_id: int | None = None
    document_id: int | None = None
    task_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"p0-cleanup-user-{suffix}", api_key=f"p0-cleanup-key-{suffix}"
        )
        company = Company(name=f"p0-cleanup-company-{suffix}")
        db.add_all((user, company))
        db.flush()
        db.add(
            CompanyMember(
                company_id=company.id,
                user_id=user.id,
                role="owner",
                status="approved",
            )
        )
        source = BusinessDataSource(
            company_id=company.id,
            name="p0-cleanup-source",
            connection_config={"host": "test"},
            credential_env_var="TEST_PASSWORD",
            status="ready",
        )
        db.add(source)
        db.flush()
        snapshot = SchemaSnapshot(
            data_source_id=source.id,
            fingerprint="a" * 64,
            catalog={"tables": {}},
            discovered_by_user_id=user.id,
        )
        db.add(snapshot)
        db.flush()
        source.active_schema_snapshot_id = snapshot.id
        set_tenant_scope(db, company.id)
        document = Documents(
            uploaded_by_user_id=user.id,
            company_id=company.id,
            name="interrupted-evaluation-document.txt",
            content="orphaned evaluation document",
            source="events/interrupted-evaluation-document.txt",
            sha256="b" * 64,
            status="completed",
        )
        db.add(document)
        task = AnalysisTask(
            user_id=user.id,
            company_id=company.id,
            question="private disposable evaluation question",
            status="completed",
            stage="completed",
        )
        db.add(task)
        db.commit()
        user_id, company_id = user.id, company.id
        source_id, snapshot_id = source.id, snapshot.id
        document_id = document.id
        task_id = task.id
        manifest_path = tmp_path / "prepare.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "harness_version": "p0-2-persisted-baseline-v1",
                    "cleanup": {
                        "state": "pending",
                        "resource_ids": {
                            "user_id": user_id,
                            "company_id": company_id,
                            "data_source_id": source_id,
                            "schema_snapshot_id": snapshot_id,
                        },
                    },
                    "documents": [],
                    "task_map": {"terminal-case": task_id},
                }
            ),
            encoding="utf-8",
        )

        cleanup(manifest_path=manifest_path)

        trace = (tmp_path / "traces" / f"task-{task_id}.html").read_text(
            encoding="utf-8"
        )
        assert f"Task</td><td>{task_id}" in trace
        assert "private disposable evaluation question" not in trace

        with SessionLocal() as verification_db:
            assert verification_db.get(User, user_id) is None
            assert verification_db.get(Company, company_id) is None
            assert verification_db.get(BusinessDataSource, source_id) is None
            assert verification_db.get(SchemaSnapshot, snapshot_id) is None
            assert verification_db.get(Documents, document_id) is None
    finally:
        db.close()
        with SessionLocal() as cleanup_db:
            if document_id is not None:
                document = cleanup_db.get(Documents, document_id)
                if document is not None:
                    cleanup_db.delete(document)
                    cleanup_db.flush()
            if snapshot_id is not None:
                snapshot = cleanup_db.get(SchemaSnapshot, snapshot_id)
                if snapshot is not None:
                    cleanup_db.delete(snapshot)
                    cleanup_db.flush()
            if source_id is not None:
                source = cleanup_db.get(BusinessDataSource, source_id)
                if source is not None:
                    cleanup_db.delete(source)
                    cleanup_db.flush()
            if company_id is not None:
                company = cleanup_db.get(Company, company_id)
                if company is not None:
                    cleanup_db.delete(company)
                    cleanup_db.flush()
            if user_id is not None:
                user = cleanup_db.get(User, user_id)
                if user is not None:
                    cleanup_db.delete(user)
            cleanup_db.commit()
