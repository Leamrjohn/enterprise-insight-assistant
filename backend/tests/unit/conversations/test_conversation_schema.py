from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationMessageCreate,
    ConversationMessageOut,
)


def test_conversation_title_cannot_be_blank_when_provided() -> None:
    with pytest.raises(ValidationError):
        ConversationCreate(title="   ")


def test_user_message_content_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        ConversationMessageCreate(content="   ")


def test_user_message_rejects_duplicate_or_non_positive_artifact_versions() -> None:
    with pytest.raises(ValidationError):
        ConversationMessageCreate(content="分析附件", artifact_version_ids=[7, 7])
    with pytest.raises(ValidationError):
        ConversationMessageCreate(content="分析附件", artifact_version_ids=[0])


def test_queued_assistant_message_allows_null_content() -> None:
    now = datetime.now(timezone.utc)

    message = ConversationMessageOut(
        id=1,
        conversation_id=2,
        role="assistant",
        content=None,
        status="queued",
        analysis_task_id=3,
        created_at=now,
        updated_at=now,
    )

    assert message.content is None


def test_clarification_assistant_message_is_a_valid_terminal_message() -> None:
    now = datetime.now(timezone.utc)

    message = ConversationMessageOut(
        id=1,
        conversation_id=2,
        role="assistant",
        content="请补充时间范围。",
        status="needs_clarification",
        analysis_task_id=3,
        created_at=now,
        updated_at=now,
    )

    assert message.status == "needs_clarification"


@pytest.mark.parametrize("field,value", [("role", "system"), ("status", "retrying")])
def test_message_output_rejects_unknown_role_or_status(field: str, value: str) -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "id": 1,
        "conversation_id": 2,
        "role": "assistant",
        "content": None,
        "status": "queued",
        "analysis_task_id": 3,
        "created_at": now,
        "updated_at": now,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ConversationMessageOut.model_validate(payload)
