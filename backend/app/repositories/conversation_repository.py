"""Database operations for conversations and their display messages."""


from sqlalchemy import  func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationMessage


def create_conversation(
    db: Session,
    *,
    user_id: int,
    title: str | None,
) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    db.flush()
    return conversation


def get_conversation_by_id(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
) -> Conversation | None:
    return (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )


def get_conversations(db: Session, *, user_id: int) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .all()
    )


def create_message(
    db: Session,
    *,
    conversation_id: int,
    role: str,
    content: str | None,
    status: str,
    analysis_task_id: int | None = None,
) -> ConversationMessage:
    message = ConversationMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        status=status,
        analysis_task_id=analysis_task_id,
    )
    db.add(message)
    db.flush()
    return message


def get_messages(
    db: Session,
    *,
    conversation_id: int,
) -> list[ConversationMessage]:
    return (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .all()
    )


def get_assistant_message_by_task_id(
    db: Session,
    *,
    task_id: int,
) -> ConversationMessage | None:
    return (
        db.query(ConversationMessage)
        .filter(
            ConversationMessage.analysis_task_id == task_id,
            ConversationMessage.role == "assistant",
        )
        .first()
    )


def touch_conversation(db: Session, *, conversation_id: int) -> None:
    db.query(Conversation).filter(Conversation.id == conversation_id).update(
        {Conversation.updated_at: func.now()},
        synchronize_session=False,
    )


def get_recent_context_messages(
    db: Session,
    *,
    conversation_id: int,
    before_message_id: int,
    limit: int,
) -> list[ConversationMessage]:
    messages = (
        db.query(ConversationMessage)
        .filter(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.id < before_message_id,
            ConversationMessage.content.is_not(None),
            ConversationMessage.status.in_(("completed", "partial")),
        )
        .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(messages))
