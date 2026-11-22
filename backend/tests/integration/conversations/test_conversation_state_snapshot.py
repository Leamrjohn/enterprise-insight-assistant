"""M7: a new task freezes the conversation state; its publish saves it once."""

from types import SimpleNamespace

import app.modules.conversations.api as conversations_api
from app.core.settings import get_settings
from app.db.session import set_tenant_scope
from app.modules.conversations.models import Conversation
from app.modules.conversations.state import (
    STATE_SNAPSHOT_KEY,
    empty_state,
    load_state,
    save_state,
)
from app.modules.identity.models import User
from app.modules.workflow import tasks
from app.modules.workflow.models import AnalysisTask
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.integration.conversations.test_conversations import (
    _setup_company_data_source,
)


def _with_region(value: str) -> dict:
    state = empty_state()
    state["constraints"]["region"] = {
        "op": "include",
        "value": value,
        "source_message_id": 1,
        "quote": f"只看{value}区",
    }
    return state


def _send(client: TestClient, db_session: Session, conversation_id: int, text: str):
    response = client.post(
        f"/conversations/{conversation_id}/messages", json={"content": text}
    )
    assert response.status_code == 202
    payload = response.json()
    task = db_session.get(AnalysisTask, payload["task_id"])
    assert task is not None
    return task, payload["user_message"]["id"]


def _conversation(client, db_session, test_user, monkeypatch) -> Conversation:
    source_id = _setup_company_data_source(client, db_session, test_user)
    conversation_id = client.post(
        "/conversations", json={"title": "状态", "data_source_id": source_id}
    ).json()["id"]
    monkeypatch.setattr(
        conversations_api, "publish_analysis_task_event", lambda db, *, event_id: True
    )
    conversation = db_session.get(Conversation, conversation_id)
    assert conversation is not None
    return conversation


def test_off_freezes_nothing(
    client: TestClient, db_session: Session, test_user: User, monkeypatch
) -> None:
    conversation = _conversation(client, db_session, test_user, monkeypatch)
    task, _ = _send(client, db_session, conversation.id, "华东区8月销售额是多少？")

    assert STATE_SNAPSHOT_KEY not in task.context_snapshot


def test_shadow_freezes_the_state_its_version_and_the_message(
    client: TestClient, db_session: Session, test_user: User, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "conversation_state_mode", "shadow")
    conversation = _conversation(client, db_session, test_user, monkeypatch)

    first, first_message = _send(
        client, db_session, conversation.id, "后面都只看华东区。"
    )
    assert first.context_snapshot[STATE_SNAPSHOT_KEY] == {
        "state": empty_state(),
        "version": 0,
        "message_id": first_message,
    }

    set_tenant_scope(db_session, conversation.company_id)
    assert save_state(
        db_session,
        conversation_id=conversation.id,
        company_id=conversation.company_id,
        state=_with_region("华东"),
        expected_version=0,
    )
    second, _ = _send(client, db_session, conversation.id, "8月销售额是多少？")
    frozen = second.context_snapshot[STATE_SNAPSHOT_KEY]
    assert (frozen["version"], frozen["state"]) == (1, _with_region("华东"))


def test_a_stale_publish_keeps_the_newer_state(
    client: TestClient, db_session: Session, test_user: User, monkeypatch
) -> None:
    conversation = _conversation(client, db_session, test_user, monkeypatch)
    set_tenant_scope(db_session, conversation.company_id)

    def publish(version: int, state: dict) -> None:
        record = SimpleNamespace(
            id=None,
            conversation_id=conversation.id,
            company_id=conversation.company_id,
            context_snapshot={STATE_SNAPSHOT_KEY: {"version": version}},
        )
        tasks._save_conversation_state(db_session, record, state)

    publish(0, _with_region("华东"))
    # A second task froze version 0 too, but publishes after the first one.
    publish(0, _with_region("华南"))
    loaded = load_state(db_session, conversation.id)
    assert (loaded.version, loaded.state) == (1, _with_region("华东"))

    publish(1, _with_region("华南"))
    loaded = load_state(db_session, conversation.id)
    assert (loaded.version, loaded.state) == (2, _with_region("华南"))
