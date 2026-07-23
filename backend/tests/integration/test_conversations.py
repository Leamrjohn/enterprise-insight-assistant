from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

import app.api.conversations as conversations_api
import app.repositories.conversation_repository as conversation_repository
import app.services.conversation_service as conversation_service
from app.core.auth import get_current_user
from app.main import app
from app.models.analysis_task import AnalysisTask
from app.models.conversation import ConversationMessage
from app.models.user import User


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


def test_create_list_and_get_conversation(client: TestClient) -> None:
    first = client.post("/conversations", json={"title": "第一个会话"})
    second = client.post("/conversations", json={"title": "第二个会话"})

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
    monkeypatch,
) -> None:
    conversation_id = client.post(
        "/conversations", json={"title": "华东区销售下降分析"}
    ).json()["id"]
    delayed_task_ids: list[int] = []

    def fake_delay(*, task_id: int) -> None:
        stored = db_session.get(AnalysisTask, task_id)
        assert stored is not None
        assert stored.input_message_id is not None
        delayed_task_ids.append(task_id)

    monkeypatch.setattr(conversations_api.process_analysis_task, "delay", fake_delay)

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "华东区 2025 年 8 月销售额为什么比 7 月下降？"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert delayed_task_ids == [payload["task_id"]]
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


def test_send_message_persists_only_the_recent_context_window(
    client: TestClient,
    db_session: Session,
    test_user: User,
    monkeypatch,
) -> None:
    conversation_id = client.post(
        "/conversations", json={"title": "上下文窗口"}
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
        conversations_api.process_analysis_task,
        "delay",
        lambda *, task_id: None,
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
    conversation_id = client.post("/conversations", json={"title": "private"}).json()[
        "id"
    ]
    other_user = User(name="conversation-other", api_key="conversation-other-key")
    db_session.add(other_user)
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


def test_enqueue_failure_compensates_task_and_assistant_message(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    conversation_id = client.post("/conversations", json={"title": None}).json()["id"]

    def fail_delay(*, task_id: int) -> None:
        raise ConnectionError(f"broker unavailable for task {task_id}")

    monkeypatch.setattr(conversations_api.process_analysis_task, "delay", fail_delay)

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "请分析销售额"},
    )

    assert response.status_code == 503
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
    assert task.status == "failed"
    assert task.stage == "queued"
    assert task.error_message == "任务暂未成功提交，请稍后重试。"
    assert assistant.status == "failed"
    assert assistant.content == "任务暂未成功提交，请稍后重试。"


def test_message_bundle_rolls_back_and_does_not_enqueue_when_insert_fails(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    conversation_id = client.post("/conversations", json={"title": "rollback"}).json()[
        "id"
    ]
    original_create_message = conversation_service.create_message
    create_calls = 0
    delayed_task_ids: list[int] = []

    def fail_second_message(*args, **kwargs):
        nonlocal create_calls
        create_calls += 1
        if create_calls == 2:
            raise RuntimeError("assistant insert failed")
        return original_create_message(*args, **kwargs)

    monkeypatch.setattr(conversation_service, "create_message", fail_second_message)
    monkeypatch.setattr(
        conversations_api.process_analysis_task,
        "delay",
        lambda *, task_id: delayed_task_ids.append(task_id),
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
    assert delayed_task_ids == []
