from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.modules.conversations.api as conversations_api
import app.modules.conversations.repository as conversation_repository
import app.modules.conversations.service as conversation_service
from app.modules.identity.authentication import get_current_user
from app.main import app
from app.modules.workflow.models import AnalysisTask
from app.modules.organizations.models import (
    BusinessDataSource,
    Company,
    CompanyMember,
    SchemaSnapshot,
)
from app.modules.conversations.models import ConversationMessage
from app.modules.workflow.outbox_models import AnalysisTaskOutboxEvent
from app.modules.identity.models import User


def _setup_company_data_source(
    client: TestClient, db_session: Session, test_user: User
) -> int:
    company = client.post("/companies", json={"name": "Acme"})
    assert company.status_code == 201
    source = BusinessDataSource(
        company_id=company.json()["id"],
        name="business-db",
        connection_config={"host": "db", "database": "business", "user": "readonly"},
        credential_env_var="BUSINESS_DATABASE_PASSWORD",
    )
    db_session.add(source)
    db_session.flush()
    snapshot = SchemaSnapshot(
        data_source_id=source.id,
        fingerprint="a" * 64,
        catalog={"tables": {}},
        discovered_by_user_id=test_user.id,
    )
    db_session.add(snapshot)
    db_session.flush()
    source.active_schema_snapshot_id = snapshot.id
    source.status = "ready"
    db_session.flush()
    return source.id


def test_recent_context_messages_are_scoped_filtered_and_ordered(
    db_session: Session,
    test_user: User,
) -> None:
    get_recent_context_messages = getattr(
        conversation_repository,
        "get_recent_context_messages",
        None,
    )
    assert callable(get_recent_context_messages), (
        "conversation_repository.get_recent_context_messages 尚未实现"
    )

    conversation = conversation_repository.create_conversation(
        db_session,
        user_id=test_user.id,
        title="上下文测试",
    )
    other_conversation = conversation_repository.create_conversation(
        db_session,
        user_id=test_user.id,
        title="其他会话",
    )
    previous_user = conversation_repository.create_message(
        db_session,
        conversation_id=conversation.id,
        role="user",
        content="分析华东区 2025 年 8 月比 7 月的销售变化",
        status="completed",
    )
    previous_assistant = conversation_repository.create_message(
        db_session,
        conversation_id=conversation.id,
        role="assistant",
        content="华东区销售额出现下降。",
        status="partial",
    )
    conversation_repository.create_message(
        db_session,
        conversation_id=conversation.id,
        role="assistant",
        content="不应进入上下文的失败消息",
        status="failed",
    )
    current_user = conversation_repository.create_message(
        db_session,
        conversation_id=conversation.id,
        role="user",
        content="那华南区呢？",
        status="completed",
    )
    conversation_repository.create_message(
        db_session,
        conversation_id=other_conversation.id,
        role="user",
        content="不应跨会话读取",
        status="completed",
    )

    messages = get_recent_context_messages(
        db_session,
        conversation_id=conversation.id,
        before_message_id=current_user.id,
        limit=8,
    )

    assert [message.id for message in messages] == [
        previous_user.id,
        previous_assistant.id,
    ]


def test_create_list_and_get_conversation(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    source_id = _setup_company_data_source(client, db_session, test_user)
    first = client.post(
        "/conversations", json={"title": "第一个会话", "data_source_id": source_id}
    )
    second = client.post(
        "/conversations", json={"title": "第二个会话", "data_source_id": source_id}
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["title"] == "第一个会话"
    assert first.json()["created_at"] is not None

    listed = client.get("/conversations")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [
        second.json()["id"],
        first.json()["id"],
    ]

    detail = client.get(f"/conversations/{first.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == first.json()["id"]
    assert "messages" not in detail.json()


def test_send_message_creates_messages_and_task_after_commit(
    client: TestClient,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    source_id = _setup_company_data_source(client, db_session, test_user)
    conversation_id = client.post(
        "/conversations",
        json={"title": "华东区销售下降分析", "data_source_id": source_id},
    ).json()["id"]
    published_task_ids: list[int] = []

    def fake_publish(db: Session, *, event_id: int) -> bool:
        event = db.get(AnalysisTaskOutboxEvent, event_id)
        assert event is not None
        stored = db_session.get(AnalysisTask, event.task_id)
        assert stored is not None
        assert stored.input_message_id is not None
        published_task_ids.append(event.task_id)
        return True

    monkeypatch.setattr(conversations_api, "publish_analysis_task_event", fake_publish)

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        headers={"X-Request-ID": "create-task-correlation-id"},
        json={"content": "华东区 2025 年 8 月销售额为什么比 7 月下降？"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert published_task_ids == [payload["task_id"]]
    assert payload["status"] == "queued"
    assert payload["user_message"]["role"] == "user"
    assert payload["user_message"]["status"] == "completed"
    assert payload["user_message"]["analysis_task_id"] is None
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["assistant_message"]["content"] is None
    assert payload["assistant_message"]["status"] == "queued"
    assert payload["assistant_message"]["analysis_task_id"] == payload["task_id"]

    task = db_session.get(AnalysisTask, payload["task_id"])
    assert task is not None
    assert task.conversation_id == conversation_id
    assert task.input_message_id == payload["user_message"]["id"]
    assert task.request_id == "create-task-correlation-id"
    assert task.context_snapshot == {
        "version": "1.0",
        "messages": [],
        "history_truncated": False,
    }

    messages = client.get(f"/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    assert [item["id"] for item in messages.json()] == [
        payload["user_message"]["id"],
        payload["assistant_message"]["id"],
    ]

    task_response = client.get(
        f"/conversations/{conversation_id}/tasks/{payload['task_id']}"
    )
    assert task_response.status_code == 200
    assert (
        task_response.json()["assistant_message_id"]
        == payload["assistant_message"]["id"]
    )
    assert task_response.json()["assistant_content"] is None
    assert task_response.json()["result_summary"] is None
    assert "result_data" not in task_response.json()


def test_failed_conversation_task_can_create_a_linked_retry(
    client: TestClient,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    source_id = _setup_company_data_source(client, db_session, test_user)
    conversation_id = client.post(
        "/conversations", json={"title": "重试会话", "data_source_id": source_id}
    ).json()["id"]
    published_task_ids: list[int] = []

    def fake_publish(db: Session, *, event_id: int) -> bool:
        event = db.get(AnalysisTaskOutboxEvent, event_id)
        assert event is not None
        published_task_ids.append(event.task_id)
        return True

    monkeypatch.setattr(conversations_api, "publish_analysis_task_event", fake_publish)
    original_response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "华东区销售下降原因"},
    )
    original_task_id = original_response.json()["task_id"]
    original = db_session.get(AnalysisTask, original_task_id)
    assert original is not None
    original.status = "failed"
    original.stage = "completed"
    original.error_message = "数据库临时不可用"
    db_session.flush()

    retried = client.post(
        f"/conversations/{conversation_id}/tasks/{original_task_id}/retry",
        headers={"X-Request-ID": "retry-task-correlation-id"},
    )
    assert retried.status_code == 202
    retry_task_id = retried.json()["task_id"]
    assert retry_task_id != original_task_id
    assert published_task_ids == [original_task_id, retry_task_id]

    retry = db_session.get(AnalysisTask, retry_task_id)
    assert retry is not None
    assert retry.status == "queued"
    assert retry.parent_task_id == original_task_id
    assert retry.request_id == "retry-task-correlation-id"
    assert retry.question == original.question
    assert retry.context_snapshot == original.context_snapshot
    assert retry.schema_snapshot_id == original.schema_snapshot_id
    assert retry.input_message_id is None
    assert retried.json()["assistant_message"]["analysis_task_id"] == retry_task_id

    non_terminal = client.post(
        f"/conversations/{conversation_id}/tasks/{retry_task_id}/retry"
    )
    assert non_terminal.status_code == 409


def test_conversation_requires_a_ready_data_source(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    company = client.post("/companies", json={"name": "Acme"})
    assert company.status_code == 201
    company_id = company.json()["id"]
    source = BusinessDataSource(
        company_id=company_id,
        name="not-ready-db",
        connection_config={"host": "db", "database": "business", "user": "readonly"},
        credential_env_var="BUSINESS_DATABASE_PASSWORD",
        status="pending",
    )
    db_session.add(source)
    db_session.flush()

    response = client.post(
        "/conversations", json={"title": "不应创建", "data_source_id": source.id}
    )
    assert response.status_code == 409
    assert "尚未准备好" in response.json()["message"]


def test_send_message_persists_only_the_recent_context_window(
    client: TestClient,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    source_id = _setup_company_data_source(client, db_session, test_user)
    conversation_id = client.post(
        "/conversations", json={"title": "上下文窗口", "data_source_id": source_id}
    ).json()["id"]
    previous_messages = []
    for index in range(9):
        previous_messages.append(
            conversation_repository.create_message(
                db_session,
                conversation_id=conversation_id,
                role="user" if index % 2 == 0 else "assistant",
                content=f"历史消息 {index + 1}",
                status="completed",
            )
        )

    monkeypatch.setattr(
        conversations_api,
        "publish_analysis_task_event",
        lambda db, *, event_id: True,
    )

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "请基于此前讨论继续分析"},
    )

    assert response.status_code == 202
    task = db_session.get(AnalysisTask, response.json()["task_id"])
    assert task is not None
    assert task.context_snapshot == {
        "version": "1.0",
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "content_truncated": False,
            }
            for message in previous_messages[-8:]
        ],
        "history_truncated": False,
    }


def test_conversation_resources_are_hidden_from_another_user(
    client: TestClient,
    db_session: Session,
    test_user: User,
) -> None:
    source_id = _setup_company_data_source(client, db_session, test_user)
    conversation_id = client.post(
        "/conversations", json={"title": "private", "data_source_id": source_id}
    ).json()["id"]
    other_user = User(name="conversation-other", api_key="conversation-other-key")
    other_company = Company(name="Other")
    db_session.add_all([other_user, other_company])
    db_session.flush()
    db_session.add(
        CompanyMember(
            company_id=other_company.id,
            user_id=other_user.id,
            role="owner",
            status="approved",
        )
    )
    db_session.flush()

    app.dependency_overrides[get_current_user] = lambda: other_user
    try:
        assert client.get(f"/conversations/{conversation_id}").status_code == 404
        assert (
            client.get(f"/conversations/{conversation_id}/messages").status_code == 404
        )
        assert (
            client.post(
                f"/conversations/{conversation_id}/messages",
                json={"content": "试图越权"},
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides[get_current_user] = lambda: test_user


def test_enqueue_failure_leaves_durable_pending_outbox_event(
    client: TestClient,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    source_id = _setup_company_data_source(client, db_session, test_user)
    conversation_id = client.post(
        "/conversations", json={"title": None, "data_source_id": source_id}
    ).json()["id"]

    def fail_publish(db: Session, *, event_id: int) -> bool:
        event = db.get(AnalysisTaskOutboxEvent, event_id)
        assert event is not None
        event.publish_attempt_count += 1
        event.last_error = "ConnectionError: broker unavailable"
        db.commit()
        return False

    monkeypatch.setattr(conversations_api, "publish_analysis_task_event", fail_publish)

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "请分析销售额"},
    )

    assert response.status_code == 202
    task = (
        db_session.query(AnalysisTask)
        .filter(AnalysisTask.conversation_id == conversation_id)
        .one()
    )
    assistant = (
        db_session.query(ConversationMessage)
        .filter(ConversationMessage.analysis_task_id == task.id)
        .one()
    )
    assert task.status == "queued"
    assert task.stage == "queued"
    assert task.error_message is None
    assert assistant.status == "queued"
    assert assistant.content is None
    event = db_session.query(AnalysisTaskOutboxEvent).filter_by(task_id=task.id).one()
    assert event.status == "pending"
    assert event.last_error == "ConnectionError: broker unavailable"


def test_message_bundle_rolls_back_and_does_not_enqueue_when_insert_fails(
    client: TestClient,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    source_id = _setup_company_data_source(client, db_session, test_user)
    conversation_id = client.post(
        "/conversations", json={"title": "rollback", "data_source_id": source_id}
    ).json()["id"]
    original_create_message = conversation_service.create_message
    create_calls = 0
    published_event_ids: list[int] = []

    def fail_second_message(*args, **kwargs):
        nonlocal create_calls
        create_calls += 1
        if create_calls == 2:
            raise RuntimeError("assistant insert failed")
        return original_create_message(*args, **kwargs)

    monkeypatch.setattr(conversation_service, "create_message", fail_second_message)
    monkeypatch.setattr(
        conversations_api,
        "publish_analysis_task_event",
        lambda db, *, event_id: published_event_ids.append(event_id) or True,
    )

    with pytest.raises(RuntimeError, match="assistant insert failed"):
        client.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": "这次事务应该回滚"},
        )

    assert (
        db_session.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation_id)
        .count()
        == 0
    )
    assert (
        db_session.query(AnalysisTask)
        .filter(AnalysisTask.conversation_id == conversation_id)
        .count()
        == 0
    )
    assert published_event_ids == []
