import errno
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import app.modules.workflow.execution as execution_module
import app.modules.workflow.tasks as analysis_tasks
import pytest
from app.core.exceptions import RetryableModelError
from app.core.logging import request_id_context
from app.db.session import SessionLocal, set_tenant_scope
from app.main import app
from app.modules.conversations.models import Conversation, ConversationMessage
from app.modules.identity.authentication import get_current_user
from app.modules.identity.models import User
from app.modules.input_artifacts.attachment_context import TaskAttachmentContext
from app.modules.input_artifacts.models import InputArtifact, InputArtifactVersion
from app.modules.organizations.models import Company, CompanyMember
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.runtime.model_governance import (
    ModelBudgetExceeded,
    record_model_call,
    reserve_model_call,
)
from app.modules.workflow.checkpoint import WorkflowCheckpoint
from app.modules.workflow.events_models import WorkflowEvent
from app.modules.workflow.execution import (
    checkpoint_workflow_state,
    claim_execution,
    recover_expired_executions,
)
from app.modules.workflow.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask, AnalysisTaskInputArtifactVersion
from app.modules.workflow.tasks import process_analysis_task
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def create_analysis_task(
    db_session: Session,
    user_id: int,
    *,
    status: str,
    stage: str,
) -> AnalysisTask:
    task = AnalysisTask(
        user_id=user_id,
        question="test question",
        status=status,
        stage=stage,
    )
    db_session.add(task)
    db_session.flush()
    return task


def test_worker_cancellation_and_duration_use_database_time(
    db_session: Session, test_user: User, monkeypatch
) -> None:
    task = create_analysis_task(
        db_session,
        test_user.id,
        status="cancelled",
        stage="queued",
    )
    database_timestamp = datetime(2040, 1, 2, tzinfo=timezone.utc)
    task.started_at = database_timestamp - timedelta(seconds=1)
    db_session.flush()
    monkeypatch.setattr(
        analysis_tasks, "database_now", lambda db: database_timestamp
    )

    assert analysis_tasks._stop_if_cancelled(db_session, task) is True
    assert task.completed_at == database_timestamp
    assert analysis_tasks._duration_ms(db_session, task) == 1000


def test_worker_preserves_an_explicitly_empty_document_scope(monkeypatch) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    company_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"empty-scope-user-{suffix}", api_key=f"empty-scope-key-{suffix}")
        company = Company(name=f"empty-scope-company-{suffix}")
        db.add_all([user, company])
        db.flush()
        user_id, company_id = user.id, company.id
        task = AnalysisTask(
            user_id=user.id,
            company_id=company.id,
            question="明确不检索文档的分析",
            status="queued",
            stage="queued",
        )
        db.add(task)
        db.commit()
        task_id = task.id
        captured: dict[str, object] = {}

        def fake_run_analysis(question, user_id, **kwargs):
            captured["document_ids"] = kwargs["document_ids"]
            return {
                "plan": {"action": "direct_response", "route": None},
                "terminal_result": {"outcome": "direct_response"},
                "final_answer": "不读取文档。",
            }

        monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
        process_analysis_task.run(task_id=task.id)

        assert captured["document_ids"] == []
    finally:
        db.rollback()
        if task_id is not None:
            task = db.get(AnalysisTask, task_id)
            if task is not None:
                db.delete(task)
                db.flush()
        if company_id is not None:
            company = db.get(Company, company_id)
            if company is not None:
                db.delete(company)
                db.flush()
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
        db.commit()
        db.close()


def test_worker_passes_frozen_attachment_only_at_runtime(monkeypatch) -> None:
    db = SessionLocal()
    task_id: int | None = None
    version_id: int | None = None
    artifact_id: int | None = None
    user_id: int | None = None
    company_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"attachment-runtime-user-{suffix}",
            api_key=f"attachment-runtime-key-{suffix}",
        )
        company = Company(name=f"attachment-runtime-company-{suffix}")
        db.add_all([user, company])
        db.flush()
        user_id, company_id = user.id, company.id
        set_tenant_scope(db, company.id)
        artifact = InputArtifact(
            company_id=company.id,
            uploaded_by_user_id=user.id,
            kind="attachment",
        )
        db.add(artifact)
        db.flush()
        artifact_id = artifact.id
        version = InputArtifactVersion(
            artifact_id=artifact.id,
            version_number=1,
            original_filename="runtime.txt",
            raw_object_key=f"input-artifacts/quarantine/{company.id}/{suffix}",
            byte_size=12,
            sha256="a" * 64,
            status="ready",
        )
        db.add(version)
        db.flush()
        version_id = version.id
        task = AnalysisTask(
            user_id=user.id,
            company_id=company.id,
            question="分析附件",
            status="queued",
            stage="queued",
        )
        db.add(task)
        db.flush()
        task_id = task.id
        db.add(
            AnalysisTaskInputArtifactVersion(
                task_id=task.id,
                artifact_version_id=version.id,
                position=0,
            )
        )
        db.commit()

        runtime_payload = [
            {
                "artifact_version_id": version.id,
                "content_trust_level": "untrusted",
                "extracted_text": "attachment-only-runtime-content",
            }
        ]
        selection_manifest = {
            "attachment_count": 1,
            "selected_char_count": 31,
            "items": [{"artifact_version_id": version.id, "truncated": False}],
        }
        storage = object()
        captured: dict[str, object] = {}

        monkeypatch.setattr(
            analysis_tasks,
            "get_artifact_processing_storage",
            lambda _settings: storage,
        )

        def fake_attachment_context(db, *, task_id, company_id, storage):
            captured["attachment_context_args"] = (task_id, company_id, storage)
            return TaskAttachmentContext(runtime_payload, selection_manifest)

        def fake_run_analysis(question, user_id, **kwargs):
            captured["attachment_context"] = kwargs["attachment_context"]
            return {
                "plan": {"action": "direct_response", "route": None},
                "terminal_result": {"outcome": "direct_response"},
                "final_answer": "附件范围已接入。",
            }

        monkeypatch.setattr(
            analysis_tasks, "build_task_attachment_context", fake_attachment_context
        )
        monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)

        process_analysis_task.run(task_id=task.id)

        assert captured["attachment_context_args"] == (task.id, company.id, storage)
        assert captured["attachment_context"] == runtime_payload
        event = (
            db.query(WorkflowEvent)
            .filter(
                WorkflowEvent.execution_attempt_id.is_not(None),
                WorkflowEvent.event_type == "context_selected",
            )
            .order_by(WorkflowEvent.id.desc())
            .first()
        )
        assert event is not None
        assert event.details["attachments"] == selection_manifest
        assert "attachment-only-runtime-content" not in str(event.details)
    finally:
        db.rollback()
        if task_id is not None:
            task = db.get(AnalysisTask, task_id)
            if task is not None:
                db.delete(task)
                db.flush()
        if version_id is not None:
            version = db.get(InputArtifactVersion, version_id)
            if version is not None:
                db.delete(version)
                db.flush()
        if artifact_id is not None:
            artifact = db.get(InputArtifact, artifact_id)
            if artifact is not None:
                db.delete(artifact)
                db.flush()
        if company_id is not None:
            company = db.get(Company, company_id)
            if company is not None:
                db.delete(company)
                db.flush()
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
        db.commit()
        db.close()


def create_conversation_analysis_task(
    db: Session,
    user_id: int,
    *,
    question: str,
    status: str = "queued",
    stage: str = "queued",
    company_id: int | None = None,
) -> tuple[AnalysisTask, ConversationMessage]:
    conversation = Conversation(
        user_id=user_id,
        company_id=company_id,
        title="worker conversation",
    )
    db.add(conversation)
    db.flush()
    user_message = ConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content=question,
        status="completed",
    )
    db.add(user_message)
    db.flush()
    task = AnalysisTask(
        user_id=user_id,
        conversation_id=conversation.id,
        input_message_id=user_message.id,
        question=question,
        status=status,
        stage=stage,
        company_id=company_id,
    )
    db.add(task)
    db.flush()
    assistant = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=None,
        status="queued",
        analysis_task_id=task.id,
    )
    db.add(assistant)
    db.flush()
    return task, assistant


def create_company_context(db: Session, user_id: int) -> Company:
    company = Company(name=f"task-company-{user_id}")
    db.add(company)
    db.flush()
    db.add(
        CompanyMember(
            company_id=company.id,
            user_id=user_id,
            role="owner",
            status="approved",
        )
    )
    db.flush()
    return company


def test_cancel_queued_task(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    company = create_company_context(db_session, test_user.id)
    task, _ = create_conversation_analysis_task(
        db_session, test_user.id, question="test question", company_id=company.id
    )

    response = client.post(
        f"/conversations/{task.conversation_id}/tasks/{task.id}/cancel"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_task_updates_assistant_message(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    company = create_company_context(db_session, test_user.id)
    task, assistant = create_conversation_analysis_task(
        db_session,
        test_user.id,
        question="cancel this analysis",
        company_id=company.id,
    )

    response = client.post(
        f"/conversations/{task.conversation_id}/tasks/{task.id}/cancel"
    )

    assert response.status_code == 200
    db_session.refresh(assistant)
    assert assistant.status == "cancelled"
    assert assistant.content == "本次分析已取消。"


def test_cannot_cancel_completed_task(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    company = create_company_context(db_session, test_user.id)
    task, _ = create_conversation_analysis_task(
        db_session,
        test_user.id,
        question="test question",
        status="completed",
        stage="completed",
        company_id=company.id,
    )

    assert (
        client.post(
            f"/conversations/{task.conversation_id}/tasks/{task.id}/cancel"
        ).status_code
        == 409
    )


def test_conversation_task_detail_hides_internal_planner_attempts(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    company = create_company_context(db_session, test_user.id)
    task, _ = create_conversation_analysis_task(
        db_session,
        test_user.id,
        question="test question",
        status="completed",
        stage="completed",
        company_id=company.id,
    )
    task.result_data = {
        "type": "langgraph_workflow",
        "planner_result": {
            "status": "ready",
            "attempts": {"model_attempts": 2},
        },
    }
    db_session.flush()

    response = client.get(f"/conversations/{task.conversation_id}/tasks/{task.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "result_data" not in response.json()


def test_task_detail_returns_stable_top_level_report(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    company = create_company_context(db_session, test_user.id)
    task, _ = create_conversation_analysis_task(
        db_session,
        test_user.id,
        question="test question",
        status="completed",
        stage="completed",
        company_id=company.id,
    )
    task.result_data = {
        "report": {
            "schema_version": "1.0",
            "status": "partial",
            "executive_summary": "已确认数据事实，但资料不足。",
            "confirmed_facts": [],
            "hypotheses": [],
            "recommendations": [],
            "data_evidence": [],
            "document_citations": [],
            "limitations": [
                {
                    "code": "insufficient_documents",
                    "message": "资料不足。",
                    "next_step": "上传相关业务资料。",
                }
            ],
        }
    }
    db_session.flush()

    response = client.get(f"/conversations/{task.conversation_id}/tasks/{task.id}")

    assert response.status_code == 200
    assert response.json()["report"] == FinalAnalysisReport.model_validate(
        task.result_data["report"]
    ).model_dump(mode="json")


def test_other_user_cannot_cancel_task(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    company = create_company_context(db_session, test_user.id)
    task, _ = create_conversation_analysis_task(
        db_session, test_user.id, question="test question", company_id=company.id
    )
    other_user = User(name="other-user", api_key="other-api-key")
    db_session.add(other_user)
    db_session.flush()
    create_company_context(db_session, other_user.id)

    def override_other_user() -> User:
        return other_user

    def override_test_user() -> User:
        return test_user

    app.dependency_overrides[get_current_user] = override_other_user
    try:
        assert (
            client.post(
                f"/conversations/{task.conversation_id}/tasks/{task.id}/cancel"
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides[get_current_user] = override_test_user


def test_worker_skips_cancelled_task(monkeypatch) -> None:
    def fail_if_graph_runs(*args, **kwargs) -> None:
        raise AssertionError("cancelled task must not enter LangGraph")

    monkeypatch.setattr(analysis_tasks, "run_analysis", fail_if_graph_runs)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"worker-user-{suffix}", api_key=f"worker-key-{suffix}")
        db.add(user)
        db.flush()
        task = AnalysisTask(
            user_id=user.id,
            question="test question",
            status="cancelled",
            stage="queued",
        )
        db.add(task)
        db.commit()
        task_id, user_id = task.id, user.id

        process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "cancelled"
        assert stored_task.attempt_count == 0
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_runs_langgraph_and_saves_terminal_planner_result(monkeypatch) -> None:
    calls = []
    context = {
        "version": "1.0",
        "messages": [{"id": 101, "role": "user", "content": "分析华东区销售额"}],
        "history_truncated": False,
    }

    def fake_run_analysis(
        question: str,
        user_id: int,
        *,
        company_id: int | None = None,
        conversation_context: dict | None = None,
        stage_callback=None,
        **kwargs,
    ) -> dict:
        calls.append((question, user_id, conversation_context))
        return {
            "plan": {"action": "scope_exit", "route": None, "reason": "范围外"},
            "planner_result": {
                "status": "ready",
                "attempts": {"model_attempts": 2},
            },
            "terminal_result": {"outcome": "scope_exit", "reason": "范围外"},
            "final_answer": "我目前只处理经营数据和内部资料分析。",
            "data_result": None,
            "knowledge_result": None,
            "review_result": None,
        }

    monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"graph-user-{suffix}", api_key=f"graph-key-{suffix}")
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id,
            question="写一首诗",
            status="queued",
            stage="queued",
            context_snapshot=context,
        )
        db.add(task)
        db.commit()
        task_id = task.id

        process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert calls == [("写一首诗", user_id, context)]
        assert stored_task is not None
        assert stored_task.status == "completed"
        assert stored_task.stage == "completed"
        assert stored_task.result_data is not None
        assert stored_task.result_data["type"] == "langgraph_workflow"
        assert stored_task.result_data["planner_result"] == {
            "status": "ready",
            "attempts": {"model_attempts": 2},
        }
        assert stored_task.result_data["terminal_result"]["outcome"] == "scope_exit"
        context_event = (
            db.query(WorkflowEvent)
            .filter(
                WorkflowEvent.task_id == task_id,
                WorkflowEvent.event_type == "context_selected",
            )
            .one()
        )
        assert context_event.details["conversation"] == {
            "snapshot_version": "1.0",
            "history_truncated": False,
            "manifest": None,
        }
        assert context_event.details["planner_memory"]["version"] == "planner-memory/v1"
        assert "content" not in str(context_event.details)
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_sets_and_restores_persisted_request_correlation(monkeypatch) -> None:
    observed_request_ids: list[str] = []

    def fake_run_analysis(*args, **kwargs) -> dict:
        observed_request_ids.append(request_id_context.get())
        return {
            "plan": {"action": "scope_exit", "route": None},
            "planner_result": {"status": "ready", "attempts": {"model_attempts": 0}},
            "terminal_result": {"outcome": "scope_exit"},
            "final_answer": "范围外。",
        }

    monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"trace-user-{suffix}", api_key=f"trace-key-{suffix}")
        db.add(user)
        db.flush()
        task = AnalysisTask(
            user_id=user.id,
            question="范围外问题",
            status="queued",
            stage="queued",
            request_id="worker-correlation-id",
        )
        db.add(task)
        db.commit()
        task_id, user_id = task.id, user.id

        process_analysis_task.run(task_id=task_id)

        assert observed_request_ids == ["worker-correlation-id"]
        assert request_id_context.get() == "-"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_syncs_running_and_completed_assistant_message(monkeypatch) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    assistant_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"conversation-worker-{suffix}", api_key=f"key-{suffix}")
        db.add(user)
        db.flush()
        task, assistant = create_conversation_analysis_task(
            db,
            user.id,
            question="你好",
        )
        db.commit()
        task_id, user_id, assistant_id = task.id, user.id, assistant.id

        def fake_run_analysis(
            question: str,
            user_id: int,
            *,
            company_id: int | None = None,
            conversation_context: dict | None = None,
            stage_callback=None,
            **kwargs,
        ) -> dict:
            independent_db = SessionLocal()
            try:
                running_message = independent_db.get(ConversationMessage, assistant_id)
                assert running_message is not None
                assert running_message.status == "running"
            finally:
                independent_db.close()
            return {
                "plan": {"action": "direct_response", "route": None},
                "planner_result": {
                    "status": "ready",
                    "attempts": {"model_attempts": 1},
                },
                "terminal_result": {"outcome": "direct_response"},
                "final_answer": "你好，我可以协助经营分析。",
            }

        monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)

        process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        stored_assistant = db.get(ConversationMessage, assistant_id)
        assert stored_task is not None
        assert stored_task.status == "completed"
        assert stored_assistant is not None
        assert stored_assistant.status == "completed"
        assert stored_assistant.content == "你好，我可以协助经营分析。"
        assert not hasattr(stored_assistant, "result_data")
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_persists_node_stage_before_node_execution(monkeypatch) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"stage-user-{suffix}", api_key=f"stage-key-{suffix}")
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        def fake_run_analysis(question, user_id, *, stage_callback=None, **kwargs):
            assert stage_callback is not None
            stage_callback("querying_data")
            independent_db = SessionLocal()
            try:
                stored = independent_db.get(AnalysisTask, task_id)
                assert stored is not None
                assert stored.status == "running"
                assert stored.stage == "querying_data"
            finally:
                independent_db.close()
            return {
                "plan": {"action": "direct_response", "route": None},
                "terminal_result": {"outcome": "direct_response"},
                "final_answer": "分析完成。",
            }

        monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
        process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.stage == "completed"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_syncs_partial_assistant_message(monkeypatch) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    assistant_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"conversation-partial-{suffix}", api_key=f"key-{suffix}")
        db.add(user)
        db.flush()
        task, assistant = create_conversation_analysis_task(
            db,
            user.id,
            question="销售额为什么下降？",
        )
        db.commit()
        task_id, user_id, assistant_id = task.id, user.id, assistant.id
        monkeypatch.setattr(
            analysis_tasks,
            "run_analysis",
            lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None, **kwargs: {
                "plan": {"action": "analyze", "route": "hybrid"},
                "final_answer": "销售额已下降，但资料不足以确认原因。",
                "review_result": {"review_status": "partial"},
            },
        )

        process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_assistant = db.get(ConversationMessage, assistant_id)
        assert stored_assistant is not None
        assert stored_assistant.status == "partial"
        assert stored_assistant.content == "销售额已下降，但资料不足以确认原因。"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_syncs_unexpected_failure_and_skips_terminal_redelivery(
    monkeypatch,
) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    assistant_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"conversation-failed-{suffix}", api_key=f"key-{suffix}")
        db.add(user)
        db.flush()
        task, assistant = create_conversation_analysis_task(
            db,
            user.id,
            question="触发失败",
        )
        db.commit()
        task_id, user_id, assistant_id = task.id, user.id, assistant.id

        monkeypatch.setattr(
            analysis_tasks,
            "run_analysis",
            lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None, **kwargs: (
                (_ for _ in ()).throw(RuntimeError("boom"))
            ),
        )
        with pytest.raises(RuntimeError, match="boom"):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        stored_assistant = db.get(ConversationMessage, assistant_id)
        assert stored_task is not None
        assert stored_task.status == "failed"
        assert stored_assistant is not None
        assert stored_assistant.status == "failed"
        assert stored_assistant.content == "分析任务执行失败，请稍后重试。"

        monkeypatch.setattr(
            analysis_tasks,
            "run_analysis",
            lambda *args: (_ for _ in ()).throw(
                AssertionError("terminal task must not rerun")
            ),
        )
        process_analysis_task.run(task_id=task_id)
        db.refresh(stored_assistant)
        assert stored_assistant.status == "failed"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_persists_partial_workflow_result(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_tasks,
        "run_analysis",
        lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None, **kwargs: {
            "plan": {
                "action": "analyze",
                "route": "hybrid",
                "reason": "需要数据和资料。",
            },
            "terminal_result": None,
            "final_answer": "销售额已下降，但现有资料不足以确认原因。",
            "data_result": {"status": "ready", "evidence": []},
            "knowledge_result": {
                "status": "insufficient_evidence",
                "answer": "无法回答：资料不足",
                "evidences": [],
            },
            "review_result": {
                "review_status": "partial",
                "data_available": True,
                "knowledge_available": False,
                "limitations": ["未检索到足够的文档证据。"],
            },
        },
    )
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"partial-user-{suffix}", api_key=f"partial-key-{suffix}")
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id,
            question="华东区销售额为什么下降？",
            status="queued",
            stage="queued",
        )
        db.add(task)
        db.commit()
        task_id = task.id

        process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "partial"
        assert stored_task.stage == "completed"
        assert stored_task.result_data["review_result"]["review_status"] == "partial"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_persists_retryable_planner_failure_as_failed(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_tasks,
        "run_analysis",
        lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None, **kwargs: {
            "terminal_result": {
                "outcome": "failed",
                "stage": "planning",
                "retryable": True,
            },
            "final_answer": "本次分析暂未完成，请稍后重试。",
        },
    )
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"retry-user-{suffix}", api_key=f"retry-key-{suffix}")
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        with pytest.raises(analysis_tasks.RetryableAnalysisTaskError):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "retrying"
        assert stored_task.stage == "retrying"
        assert stored_task.attempt_count == 1
        assert stored_task.error_type == "RetryableAnalysisTaskError"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_retries_transient_connection_error(monkeypatch) -> None:
    def fail_after_entering_data_node(*args, **kwargs):
        kwargs["stage_callback"]("querying_data", "data_node")
        raise ConnectionError("redis down")

    monkeypatch.setattr(
        analysis_tasks,
        "run_analysis",
        fail_after_entering_data_node,
    )
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"connection-user-{suffix}", api_key=f"connection-key-{suffix}"
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        with pytest.raises(analysis_tasks.RetryableAnalysisTaskError):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "retrying"
        assert stored_task.stage == "retrying"
        assert stored_task.error_type == "ConnectionError"
        assert stored_task.attempt_count == 1
        transition = (
            db.query(WorkflowCheckpoint)
            .join(
                TaskExecutionAttempt,
                WorkflowCheckpoint.execution_attempt_id == TaskExecutionAttempt.id,
            )
            .filter(TaskExecutionAttempt.task_id == task_id)
            .order_by(WorkflowCheckpoint.id.desc())
            .first()
        )
        assert transition is not None
        assert transition.next_node == "data_node"
        assert transition.state_patch["retry_error_code"] == "ConnectionError"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_does_not_retry_disk_full_error(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_tasks,
        "run_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError(errno.ENOSPC, "No space left on device")
        ),
    )
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"disk-full-user-{suffix}", api_key=f"disk-full-key-{suffix}")
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        with pytest.raises(OSError, match="No space"):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "failed"
        assert stored_task.attempt_count == 1
        assert stored_task.error_type == "OSError"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_database_full_during_terminal_transition_keeps_execution_recoverable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        analysis_tasks,
        "run_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError(errno.ENOSPC, "No space left on device")
        ),
    )
    monkeypatch.setattr(
        analysis_tasks,
        "transition_execution",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError(errno.ENOSPC, "No space left on device")
        ),
    )
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"database-full-user-{suffix}",
            api_key=f"database-full-key-{suffix}",
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        with pytest.raises(OSError, match="No space"):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "running"
        assert stored_task.active_execution_id is not None
        attempt = (
            db.query(TaskExecutionAttempt)
            .filter(TaskExecutionAttempt.task_id == task_id)
            .one()
        )
        assert attempt.status == "running"
        attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

        assert recover_expired_executions(db) == [task_id]
        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "retrying"
        assert stored_task.active_execution_id is None
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_late_result_cannot_publish_after_execution_lease_recovery(
    monkeypatch,
) -> None:
    entered_model_call = threading.Event()
    release_model_call = threading.Event()
    worker_errors: list[Exception] = []

    def fake_run_analysis(*args, **kwargs):
        entered_model_call.set()
        assert release_model_call.wait(timeout=5)
        return {
            "plan": {"action": "direct_response", "route": None},
            "terminal_result": {"outcome": "direct_response"},
            "final_answer": "迟到的旧执行结果。",
        }

    monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    worker: threading.Thread | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"lease-recovery-user-{suffix}",
            api_key=f"lease-recovery-key-{suffix}",
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        def run_worker() -> None:
            try:
                process_analysis_task.run(task_id=task_id)
            except Exception as exc:  # noqa: BLE001 - surface arbitrary thread failure
                worker_errors.append(exc)

        worker = threading.Thread(target=run_worker)
        worker.start()
        assert entered_model_call.wait(timeout=5)

        db.expire_all()
        attempt = (
            db.query(TaskExecutionAttempt)
            .filter(TaskExecutionAttempt.task_id == task_id)
            .one()
        )
        attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

        assert recover_expired_executions(db) == [task_id]
        release_model_call.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert worker_errors == []

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "retrying"
        assert stored_task.active_execution_id is None
        assert stored_task.result_data is None
        assert stored_task.result_summary is None
        assert attempt.status == "expired"
    finally:
        release_model_call.set()
        if worker is not None:
            worker.join(timeout=5)
        _delete_created_records(db, task_id, user_id)


def test_worker_heartbeats_during_a_blocking_workflow(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "LEASE_SECONDS", 2)
    entered_model_call = threading.Event()
    heartbeat_renewed = threading.Event()
    release_model_call = threading.Event()
    worker_errors: list[Exception] = []
    original_renew = analysis_tasks.renew_execution_lease

    def observe_renew(*args, **kwargs):
        renewed = original_renew(*args, **kwargs)
        if renewed:
            heartbeat_renewed.set()
        return renewed

    def fake_run_analysis(*args, **kwargs):
        entered_model_call.set()
        assert release_model_call.wait(timeout=5)
        return {
            "plan": {"action": "direct_response", "route": None},
            "terminal_result": {"outcome": "direct_response"},
            "final_answer": "有心跳保护的长调用结果。",
        }

    monkeypatch.setattr(analysis_tasks, "renew_execution_lease", observe_renew)
    monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    worker: threading.Thread | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"heartbeat-user-{suffix}", api_key=f"heartbeat-key-{suffix}"
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        def run_worker() -> None:
            try:
                process_analysis_task.run(task_id=task_id)
            except Exception as exc:  # noqa: BLE001 - surface arbitrary thread failure
                worker_errors.append(exc)

        worker = threading.Thread(target=run_worker)
        worker.start()
        assert entered_model_call.wait(timeout=5)
        assert heartbeat_renewed.wait(timeout=4)

        db.expire_all()
        assert recover_expired_executions(db) == []
        release_model_call.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert worker_errors == []

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "completed"
        assert stored_task.result_summary == "有心跳保护的长调用结果。"
    finally:
        release_model_call.set()
        if worker is not None:
            worker.join(timeout=5)
        _delete_created_records(db, task_id, user_id)


def test_worker_heartbeat_database_failure_allows_safe_lease_recovery(
    monkeypatch,
) -> None:
    monkeypatch.setattr(execution_module, "LEASE_SECONDS", 2)
    entered_model_call = threading.Event()
    heartbeat_attempted = threading.Event()
    release_model_call = threading.Event()
    worker_errors: list[Exception] = []

    def fail_renew(*args, **kwargs):
        heartbeat_attempted.set()
        raise ConnectionError("heartbeat database unavailable")

    def fake_run_analysis(*args, **kwargs):
        entered_model_call.set()
        assert release_model_call.wait(timeout=6)
        return {
            "plan": {"action": "direct_response", "route": None},
            "terminal_result": {"outcome": "direct_response"},
            "final_answer": "数据库故障期间的旧执行结果。",
        }

    monkeypatch.setattr(analysis_tasks, "renew_execution_lease", fail_renew)
    monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    worker: threading.Thread | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"heartbeat-failure-user-{suffix}",
            api_key=f"heartbeat-failure-key-{suffix}",
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        def run_worker() -> None:
            try:
                process_analysis_task.run(task_id=task_id)
            except Exception as exc:  # noqa: BLE001 - surface arbitrary thread failure
                worker_errors.append(exc)

        worker = threading.Thread(target=run_worker)
        worker.start()
        assert entered_model_call.wait(timeout=5)
        assert heartbeat_attempted.wait(timeout=4)
        time.sleep(1.1)

        assert recover_expired_executions(db) == [task_id]
        release_model_call.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert worker_errors == []

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "retrying"
        assert stored_task.active_execution_id is None
        assert stored_task.result_data is None
        assert stored_task.result_summary is None
    finally:
        release_model_call.set()
        if worker is not None:
            worker.join(timeout=5)
        _delete_created_records(db, task_id, user_id)


def test_worker_retries_retryable_model_error(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_tasks,
        "run_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RetryableModelError("Model returned an empty JSON response")
        ),
    )
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"model-retry-user-{suffix}", api_key=f"model-retry-key-{suffix}"
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        with pytest.raises(analysis_tasks.RetryableAnalysisTaskError):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        assert stored_task is not None
        assert stored_task.status == "retrying"
        assert stored_task.stage == "retrying"
        assert stored_task.error_type == "RetryableModelError"
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_timeout_keeps_governed_call_unknown_then_retries(monkeypatch) -> None:
    def timeout_after_reservation(*args, **kwargs):
        scope = reserve_model_call(
            provider="deepseek",
            model_name="timeout-test-model",
            estimated_prompt_tokens=12,
            reserved_completion_tokens=8,
        )
        assert scope is not None
        record_model_call(
            scope,
            provider="deepseek",
            model_name="timeout-test-model",
            result_category="retryable_error",
            error_code="provider_timeout",
        )
        raise RetryableModelError("provider timeout")

    monkeypatch.setattr(analysis_tasks, "run_analysis", timeout_after_reservation)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(
            name=f"timeout-user-{suffix}", api_key=f"timeout-key-{suffix}"
        )
        db.add(user)
        db.flush()
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id, question="超时账本", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id

        with pytest.raises(analysis_tasks.RetryableAnalysisTaskError):
            process_analysis_task.run(task_id=task_id)

        db.expire_all()
        stored_task = db.get(AnalysisTask, task_id)
        record = db.query(ModelCallRecord).filter_by(task_id=task_id).one()
        assert stored_task is not None
        assert stored_task.status == "retrying"
        assert stored_task.model_budget_usage["unknown_cost_calls"] == 1
        assert record.billing_status == "unknown"
        assert record.cost is None
        assert record.error_code == "provider_timeout"
        assert record.settled_at is not None
    finally:
        _delete_created_records(db, task_id, user_id)


def _delete_created_records(
    db: Session, task_id: int | None, user_id: int | None
) -> None:
    db.rollback()
    if task_id is not None:
        task = db.get(AnalysisTask, task_id)
        if task is not None:
            db.delete(task)
            db.flush()
    if user_id is not None:
        user = db.get(User, user_id)
        if user is not None:
            db.delete(user)
    db.commit()
    db.close()


def test_worker_resumes_from_database_checkpoint(monkeypatch) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"resume-user-{suffix}", api_key=f"resume-key-{suffix}")
        db.add(user)
        db.flush()
        user_id = user.id
        task = AnalysisTask(
            user_id=user.id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id
        old = claim_execution(
            db, task_id=task.id, celery_task_id="old", worker_id="dead-worker"
        )
        assert old is not None
        assert checkpoint_workflow_state(
            db,
            attempt=old.attempt,
            stage="querying_data",
            completed_node="data_node",
            next_node="knowledge_node",
            workflow_state={
                "plan": {"action": "analyze", "route": "hybrid"},
                "data_result": {"status": "ready", "evidence": [{"rows": [[1]]}]},
            },
        )
        old.attempt.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        assert recover_expired_executions(db) == [task.id]

        captured: dict[str, object] = {}

        def fake_run_analysis(question, user_id, **kwargs):
            captured["resume_next_node"] = kwargs["resume_next_node"]
            captured["resume_state"] = kwargs["resume_state"]
            return {
                "plan": kwargs["resume_state"]["plan"],
                "final_answer": "从数据检查点恢复后完成。",
                "review_result": {"review_status": "complete"},
            }

        monkeypatch.setattr(analysis_tasks, "run_analysis", fake_run_analysis)
        process_analysis_task.run(task_id=task.id)

        db.expire_all()
        stored = db.get(AnalysisTask, task.id)
        assert stored is not None
        assert stored.status == "completed"
        assert captured["resume_next_node"] == "knowledge_node"
        assert captured["resume_state"] == {
            "plan": {"action": "analyze", "route": "hybrid"},
            "data_result": {"status": "ready", "evidence": [{"rows": [[1]]}]},
        }
    finally:
        _delete_created_records(db, task_id, user_id)


def test_worker_marks_model_budget_exhaustion_as_partial_without_retry(
    monkeypatch,
) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"budget-user-{suffix}", api_key=f"budget-key-{suffix}")
        db.add(user)
        db.flush()
        user_id = user.id
        task = AnalysisTask(
            user_id=user.id, question="销售额", status="queued", stage="queued"
        )
        db.add(task)
        db.commit()
        task_id = task.id
        monkeypatch.setattr(
            analysis_tasks,
            "run_analysis",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                ModelBudgetExceeded("model call budget exhausted")
            ),
        )

        process_analysis_task.run(task_id=task.id)

        db.expire_all()
        stored = db.get(AnalysisTask, task.id)
        assert stored is not None
        assert stored.status == "partial"
        assert stored.error_type == "model_budget_exhausted"
        assert stored.result_data["type"] == "model_budget_exhausted"
    finally:
        _delete_created_records(db, task_id, user_id)
