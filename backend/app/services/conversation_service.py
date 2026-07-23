"""Transactional orchestration for conversation APIs."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.analysis_task import AnalysisTask
from app.models.conversation import Conversation, ConversationMessage
from app.repositories.conversation_repository import (
    create_conversation,
    create_message,
    get_assistant_message_by_task_id,
    get_conversation_by_id,
    get_conversations,
    get_messages,
    touch_conversation,
    get_recent_context_messages,
)
from app.repositories.task_repository import create_task, get_task_by_id


ENQUEUE_FAILURE_MESSAGE = "任务暂未成功提交，请稍后重试。"


@dataclass(frozen=True)
class ConversationTaskBundle:
    task: AnalysisTask
    user_message: ConversationMessage
    assistant_message: ConversationMessage


def create_conversation_service(
    db: Session,
    *,
    user_id: int,
    title: str | None,
) -> Conversation:
    try:
        conversation = create_conversation(db, user_id=user_id, title=title)
        db.commit()
        db.refresh(conversation)
        return conversation
    except Exception:
        db.rollback()
        raise


def get_conversation_service(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
) -> Conversation | None:
    return get_conversation_by_id(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )


def get_conversations_service(db: Session, *, user_id: int) -> list[Conversation]:
    return get_conversations(db, user_id=user_id)


def get_conversation_messages_service(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
) -> list[ConversationMessage] | None:
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    if conversation is None:
        return None
    return get_messages(db, conversation_id=conversation.id)

MAX_CONTEXT_MESSAGES = 8

def create_conversation_task_service(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    content: str,
) -> ConversationTaskBundle | None:
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    if conversation is None:
        return None

    try:
        user_message = create_message(
            db,
            conversation_id=conversation.id,
            role="user",
            content=content,
            status="completed",
        )
        messages = get_recent_context_messages(
            db,
            conversation_id=conversation_id,
            before_message_id=user_message.id,
            limit=MAX_CONTEXT_MESSAGES,
        )
        data = build_conversation_context(messages,)
        task = create_task(
            db,
            user_id=user_id,
            question=content,
            conversation_id=conversation.id,
            input_message_id=user_message.id,
            context_snapshot=data,
        )
        assistant_message = create_message(
            db,
            conversation_id=conversation.id,
            role="assistant",
            content=None,
            status="queued",
            analysis_task_id=task.id,
        )
        touch_conversation(db, conversation_id=conversation.id)
        db.commit()
        for record in (task, user_message, assistant_message):
            db.refresh(record)
        return ConversationTaskBundle(
            task=task,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except Exception:
        db.rollback()
        raise


def compensate_enqueue_failure_service(
    db: Session,
    *,
    task_id: int,
    user_id: int,
) -> None:
    try:
        task = get_task_by_id(db, task_id=task_id, user_id=user_id)
        if task is None:
            return
        task.status = "failed"
        task.error_message = ENQUEUE_FAILURE_MESSAGE
        assistant_message = get_assistant_message_by_task_id(db, task_id=task.id)
        if assistant_message is not None:
            assistant_message.status = "failed"
            assistant_message.content = ENQUEUE_FAILURE_MESSAGE
        if task.conversation_id is not None:
            touch_conversation(db, conversation_id=task.conversation_id)
        db.commit()
    except Exception:
        db.rollback()
        raise


MAX_CONTEXT_CHARS = 6000
MAX_CONTEXT_MESSAGE_CHARS = 2000
MIN_CONTEXT_FRAGMENT_CHARS = 1000


def build_conversation_context(
    messages: list[ConversationMessage],
    *,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_message_chars: int = MAX_CONTEXT_MESSAGE_CHARS,
    min_fragment_chars: int = MIN_CONTEXT_FRAGMENT_CHARS,
) -> dict:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")

    if max_message_chars <= 0:
        raise ValueError("max_message_chars must be greater than 0")

    if min_fragment_chars <= 0:
        raise ValueError("min_fragment_chars must be greater than 0")

    if min_fragment_chars > min(max_chars, max_message_chars):
        raise ValueError(
            "min_fragment_chars cannot exceed the available message budget"
        )

    selected_messages = []
    used_chars = 0
    history_truncated = False
    message_limit = min(max_chars, max_message_chars)

    for message in reversed(messages):
        original_content = (message.content or "").strip()
        truncated = False
        if not original_content:
            continue

        content = original_content[:message_limit]
        remaining_chars = max_chars - used_chars

        if len(content) < len(original_content) or len(content) > remaining_chars:
            truncated = True

        if remaining_chars >= len(content):
            selected_messages.append(
                {
                    "id": message.id,
                    "role": message.role,
                    "content": content,
                    "content_truncated": truncated,
                }
            )
            used_chars += len(content)
            continue

        if remaining_chars >= min_fragment_chars:
            used_chars += len(content[:remaining_chars])
            selected_messages.append(
                {
                    "id": message.id,
                    "role": message.role,
                    "content": content[:remaining_chars],
                    "content_truncated": truncated,
                }
            )
        else:
            history_truncated = True
            break

    return {
        "version": "1.0",
        "messages": list(reversed(selected_messages)),
        "history_truncated": history_truncated,
    }
