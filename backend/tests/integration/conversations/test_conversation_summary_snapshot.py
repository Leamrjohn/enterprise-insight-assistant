"""C9c: a new task freezes the summary items that sit before its history."""

from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.conversations.models import ConversationMessage
from app.modules.conversations.summary import (
    SUMMARY_SNAPSHOT_KEY,
    empty_summary,
    save_summary,
)
from app.modules.identity.models import User
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.integration.conversations.test_conversation_state_snapshot import (
    _conversation,
    _send,
)


def _history(db_session: Session, conversation_id: int, count: int) -> list[int]:
    messages = [
        ConversationMessage(
            conversation_id=conversation_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"第{i + 1}条",
            status="completed",
        )
        for i in range(count)
    ]
    db_session.add_all(messages)
    db_session.flush()
    return [m.id for m in messages]


def test_off_freezes_no_summary(
    client: TestClient, db_session: Session, test_user: User, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "conversation_summary_mode", "off")
    conversation = _conversation(client, db_session, test_user, monkeypatch)
    _history(db_session, conversation.id, 10)
    task, _ = _send(client, db_session, conversation.id, "8月销售额是多少？")

    assert SUMMARY_SNAPSHOT_KEY not in task.context_snapshot


def test_shadow_freezes_only_items_older_than_the_history(
    client: TestClient, db_session: Session, test_user: User, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "conversation_summary_mode", "shadow")
    conversation = _conversation(client, db_session, test_user, monkeypatch)
    ids = _history(db_session, conversation.id, 10)
    summary = empty_summary()
    summary["items"] = [
        {"text": "用户只看华东区", "source_message_ids": [ids[0]]},
        # ids[2] is the oldest of the last eight, still in the history.
        {"text": "重复的要点", "source_message_ids": [ids[1], ids[2]]},
    ]
    set_tenant_scope(db_session, conversation.company_id)
    assert save_summary(
        db_session,
        conversation_id=conversation.id,
        company_id=conversation.company_id,
        summary=summary,
        expected_version=0,
    )

    task, _ = _send(client, db_session, conversation.id, "8月销售额是多少？")

    assert task.context_snapshot[SUMMARY_SNAPSHOT_KEY] == {
        "version": 1,
        "items": ["用户只看华东区"],
    }
