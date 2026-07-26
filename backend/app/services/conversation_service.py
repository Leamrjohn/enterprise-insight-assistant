"""Transactional orchestration for conversation APIs."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.company_auth import CurrentCompanyContext
from app.models.analysis_task import AnalysisTask
from app.models.conversation import Conversation, ConversationMessage
from app.models.documents import Documents
from app.repositories.document_repository import allowed_min_view_roles
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
from app.repositories.company_repository import (
    get_data_source,
    get_snapshot,
)
from app.services.outbox_service import create_analysis_task_event


@dataclass(frozen=True)
class ConversationTaskBundle:
    task: AnalysisTask
    outbox_event_id: int
    user_message: ConversationMessage
    assistant_message: ConversationMessage


class ConversationDocumentScopeError(ValueError):
    """A requested document is not readable in the current company role."""


class DataSourceNotReadyError(ValueError):
    """A conversation cannot run without an activated schema snapshot."""


def create_conversation_service(
    db: Session,
    *,
    context: CurrentCompanyContext,
    title: str | None,
    data_source_id: int | None = None,
) -> Conversation:
    source = (
        get_data_source(
            db, data_source_id=data_source_id, company_id=context.company.id
        )
        if data_source_id is not None
        else None
    )
    if source is None:
        raise ValueError("data source not found")
    if source.status != "ready" or source.active_schema_snapshot_id is None:
        raise DataSourceNotReadyError("该数据源尚未准备好，无法创建会话")
    try:
        conversation = create_conversation(
            db,
            user_id=context.user.id,
            title=title,
            company_id=context.company.id,
            data_source_id=data_source_id,
        )
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
    context: CurrentCompanyContext,
) -> Conversation | None:
    return get_conversation_by_id(
        db,
        conversation_id=conversation_id,
        user_id=context.user.id,
        company_id=context.company.id,
    )


def get_conversations_service(
    db: Session, *, context: CurrentCompanyContext
) -> list[Conversation]:
    return get_conversations(db, user_id=context.user.id, company_id=context.company.id)


def get_conversation_messages_service(
    db: Session,
    *,
    conversation_id: int,
    context: CurrentCompanyContext,
) -> list[ConversationMessage] | None:
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if conversation is None:
        return None
    return get_messages(db, conversation_id=conversation.id)


def get_conversation_task_service(
    db: Session,
    *,
    conversation_id: int,
    task_id: int,
    context: CurrentCompanyContext,
) -> AnalysisTask | None:
    """Return a task only through its owning current-company conversation."""
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if conversation is None:
        return None
    task = get_task_by_id(db, task_id=task_id, user_id=context.user.id)
    if task is None or task.company_id != context.company.id:
        return None
    return task if task.conversation_id == conversation.id else None


MAX_CONTEXT_MESSAGES = 8


def create_conversation_task_service(
    db: Session,
    *,
    conversation_id: int,
    context: CurrentCompanyContext,
    content: str,
    document_ids: list[int] | None = None,
) -> ConversationTaskBundle | None:
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if conversation is None:
        return None

    selected_document_ids = document_ids
    allowed_documents = (
        db.query(Documents)
        .filter(
            Documents.company_id == context.company.id,
            Documents.status == "completed",
            Documents.min_view_role.in_(allowed_min_view_roles(context.role)),
        )
        .all()
    )
    allowed_ids = {document.id for document in allowed_documents}
    if selected_document_ids is None:
        selected_document_ids = sorted(allowed_ids)
    elif not set(selected_document_ids).issubset(allowed_ids):
        raise ConversationDocumentScopeError("所选文档不存在或当前用户无权检索")

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
        conversation_context_snapshot = build_conversation_context(
            messages,
        )
        source = get_data_source(
            db,
            data_source_id=conversation.data_source_id,
            company_id=context.company.id,
        )
        if source is None or source.active_schema_snapshot_id is None:
            raise DataSourceNotReadyError("会话数据源没有可运行的契约快照")
        snapshot = get_snapshot(
            db,
            snapshot_id=source.active_schema_snapshot_id,
            data_source_id=source.id,
        )
        if snapshot is None:
            raise DataSourceNotReadyError("会话数据源的契约快照不存在")
        task = create_task(
            db,
            user_id=context.user.id,
            question=content,
            conversation_id=conversation.id,
            input_message_id=user_message.id,
            context_snapshot=conversation_context_snapshot,
            company_id=context.company.id,
            data_source_id=conversation.data_source_id,
            schema_snapshot_id=snapshot.id if snapshot else None,
            document_ids=selected_document_ids,
        )
        outbox_event = create_analysis_task_event(db, task_id=task.id)
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
            outbox_event_id=outbox_event.id,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except Exception:
        db.rollback()
        raise


def cancel_conversation_task_service(
    db: Session,
    *,
    conversation_id: int,
    task_id: int,
    context: CurrentCompanyContext,
) -> AnalysisTask | None:
    """Cancel a non-terminal conversation task and update its assistant message."""
    task = get_conversation_task_service(
        db,
        conversation_id=conversation_id,
        task_id=task_id,
        context=context,
    )
    if task is None:
        return None
    if task.status not in {"queued", "running", "retrying"}:
        raise ValueError(
            f"task {task_id} cannot be cancelled from status {task.status}"
        )
    try:
        task.status = "cancelled"
        assistant_message = get_assistant_message_by_task_id(db, task_id=task.id)
        if assistant_message is not None:
            assistant_message.status = "cancelled"
            assistant_message.content = "本次分析已取消。"
        touch_conversation(db, conversation_id=conversation_id)
        db.commit()
        db.refresh(task)
        return task
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
