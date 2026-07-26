from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.tasks.analysis_tasks as analysis_tasks
from app.core.auth import get_current_user
from app.db.session import SessionLocal
from app.main import app
from app.models.analysis_task import AnalysisTask
from app.models.company import Company, CompanyMember
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import User
from app.tasks.analysis_tasks import process_analysis_task


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
    assert response.json()["report"] == task.result_data["report"]


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
            lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None: {
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
            lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None: (
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
        lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None: {
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
        lambda question, user_id, *, company_id=None, conversation_context=None, stage_callback=None: {
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
    monkeypatch.setattr(
        analysis_tasks,
        "run_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("redis down")),
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
