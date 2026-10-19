"""Transactional orchestration for conversation APIs."""

from dataclasses import dataclass

from app.modules.conversations.models import Conversation, ConversationMessage
from app.modules.conversations.repository import (
    create_conversation,
    create_message,
    get_assistant_message_by_task_id,
    get_conversation_by_id,
    get_conversations,
    get_messages,
    get_recent_context_messages,
    touch_conversation,
)
from app.modules.documents.models import Documents
from app.modules.documents.repository import allowed_min_view_roles
from app.modules.input_artifacts.repository import (
    get_ready_owned_input_artifact_versions,
)
from app.modules.organizations.access import CurrentCompanyContext
from app.modules.organizations.repository import (
    get_data_source,
    get_snapshot,
)
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.delivery.outbox import create_analysis_task_event
from app.modules.workflow.repository import (
    cancel_task,
    create_task,
    get_task_by_id,
    get_task_document_ids,
    get_task_input_artifact_version_ids,
)
from sqlalchemy.orm import Session
from tiktoken import get_encoding


@dataclass(frozen=True)
class ConversationTaskBundle:
    task: AnalysisTask
    outbox_event_id: int
    user_message: ConversationMessage
    assistant_message: ConversationMessage


@dataclass(frozen=True)
class ConversationTaskRetryBundle:
    task: AnalysisTask
    outbox_event_id: int
    assistant_message: ConversationMessage


class ConversationDocumentScopeError(ValueError):
    """A requested document is not readable in the current company role."""


class ConversationInputArtifactScopeError(ValueError):
    """An attachment is unavailable, not ready, or not owned by the actor."""


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
    artifact_version_ids: list[int] | None = None,
    request_id: str | None = None,
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

    selected_artifact_version_ids = _resolve_ready_owned_artifact_version_ids(
        db,
        context=context,
        artifact_version_ids=artifact_version_ids or [],
    )

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
            limit=MAX_CONTEXT_MESSAGES + 1,
        )
        conversation_context_snapshot = build_conversation_context(
            messages,
        )
        if conversation.data_source_id is None:
            raise DataSourceNotReadyError("会话没有关联经营数据源")
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
            input_artifact_version_ids=selected_artifact_version_ids,
            request_id=request_id,
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
    request_id: str | None = None,
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
        cancel_task(db, task)
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


def retry_conversation_task_service(
    db: Session,
    *,
    conversation_id: int,
    task_id: int,
    context: CurrentCompanyContext,
    request_id: str | None = None,
) -> ConversationTaskRetryBundle | None:
    """Create a linked retry without mutating the original terminal task."""
    original = get_conversation_task_service(
        db,
        conversation_id=conversation_id,
        task_id=task_id,
        context=context,
    )
    if original is None:
        return None
    if original.status not in {"failed", "cancelled"}:
        raise ValueError(
            f"task {task_id} cannot be retried from status {original.status}"
        )
    if original.data_source_id is None or original.schema_snapshot_id is None:
        raise ValueError("task does not have a reusable execution scope")

    document_ids = get_task_document_ids(db, task_id=original.id)
    artifact_version_ids = _resolve_ready_owned_artifact_version_ids(
        db,
        context=context,
        artifact_version_ids=get_task_input_artifact_version_ids(db, task_id=original.id),
    )
    try:
        task = create_task(
            db,
            user_id=context.user.id,
            question=original.question,
            conversation_id=conversation_id,
            context_snapshot=original.context_snapshot,
            company_id=context.company.id,
            data_source_id=original.data_source_id,
            schema_snapshot_id=original.schema_snapshot_id,
            document_ids=document_ids,
            input_artifact_version_ids=artifact_version_ids,
            parent_task_id=original.id,
            request_id=request_id,
        )
        outbox_event = create_analysis_task_event(db, task_id=task.id)
        assistant_message = create_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=None,
            status="queued",
            analysis_task_id=task.id,
        )
        touch_conversation(db, conversation_id=conversation_id)
        db.commit()
        for record in (task, assistant_message):
            db.refresh(record)
        return ConversationTaskRetryBundle(
            task=task,
            outbox_event_id=outbox_event.id,
            assistant_message=assistant_message,
        )
    except Exception:
        db.rollback()
        raise


def _resolve_ready_owned_artifact_version_ids(
    db: Session,
    *,
    context: CurrentCompanyContext,
    artifact_version_ids: list[int],
) -> list[int]:
    if not artifact_version_ids:
        return []
    if any(
        isinstance(version_id, bool)
        or not isinstance(version_id, int)
        or version_id <= 0
        for version_id in artifact_version_ids
    ) or len(set(artifact_version_ids)) != len(artifact_version_ids):
        raise ConversationInputArtifactScopeError("附件版本标识无效")
    available_ids = {
        version.id
        for version in get_ready_owned_input_artifact_versions(
            db,
            version_ids=artifact_version_ids,
            company_id=context.company.id,
            uploaded_by_user_id=context.user.id,
        )
    }
    if set(artifact_version_ids) != available_ids:
        raise ConversationInputArtifactScopeError(
            "所选附件不存在、尚未处理完成或当前用户无权使用"
        )
    return artifact_version_ids


MAX_CONTEXT_CHARS = 6000
MAX_CONTEXT_MESSAGE_CHARS = 2000
MIN_CONTEXT_FRAGMENT_CHARS = 1000
MAX_CONTEXT_TOKENS = 2048


def estimate_conversation_tokens(text: str) -> int:
    """Use the configured-family tokenizer for deterministic history selection."""
    return len(get_encoding("o200k_base").encode(text))


def _token_limited_prefix(content: str, max_tokens: int) -> str:
    """Return the longest character prefix that fits the history token budget."""
    low, high = 0, len(content)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_conversation_tokens(content[:middle]) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    return content[:low]


def build_conversation_context(
    messages: list[ConversationMessage],
    *,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_message_chars: int = MAX_CONTEXT_MESSAGE_CHARS,
    min_fragment_chars: int = MIN_CONTEXT_FRAGMENT_CHARS,
    max_tokens: int = MAX_CONTEXT_TOKENS,
    max_messages: int = MAX_CONTEXT_MESSAGES,
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

    if max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0")

    if max_messages <= 0:
        raise ValueError("max_messages must be greater than 0")

    selected_messages = []
    manifest_fragments = []
    used_chars = 0
    used_tokens = 0
    history_truncated = False
    message_limit = min(max_chars, max_message_chars)
    budget_exhausted = False
    considered_messages = 0

    for message in reversed(messages):
        original_content = (message.content or "").strip()
        if not original_content:
            continue

        if considered_messages >= max_messages:
            manifest_fragments.append(
                {
                    "message_id": message.id,
                    "original_chars": len(original_content),
                    "selected_chars": 0,
                    "selected_tokens": 0,
                    "decision": "omitted",
                    "reason": "message_count_limit",
                }
            )
            history_truncated = True
            continue

        considered_messages += 1

        if budget_exhausted:
            manifest_fragments.append(
                {
                    "message_id": message.id,
                    "original_chars": len(original_content),
                    "selected_chars": 0,
                    "selected_tokens": 0,
                    "decision": "omitted",
                    "reason": "context_budget_exhausted",
                }
            )
            continue

        content = original_content[:message_limit]
        truncated = len(content) < len(original_content)
        remaining_chars = max_chars - used_chars
        remaining_tokens = max_tokens - used_tokens

        if len(content) <= remaining_chars and (
            content_tokens := estimate_conversation_tokens(content)
        ) <= remaining_tokens:
            selected_messages.append(
                {
                    "id": message.id,
                    "role": message.role,
                    "content": content,
                    "content_truncated": truncated,
                }
            )
            manifest_fragments.append(
                {
                    "message_id": message.id,
                    "original_chars": len(original_content),
                    "selected_chars": len(content),
                    "selected_tokens": content_tokens,
                    "decision": "truncated" if truncated else "selected",
                    "reason": "per_message_char_limit" if truncated else "within_budget",
                }
            )
            used_chars += len(content)
            used_tokens += content_tokens
            history_truncated = history_truncated or truncated
            continue

        fragment = content[:remaining_chars]
        fragment = _token_limited_prefix(fragment, remaining_tokens)
        if len(fragment) >= min_fragment_chars:
            fragment_tokens = estimate_conversation_tokens(fragment)
            selected_messages.append(
                {
                    "id": message.id,
                    "role": message.role,
                    "content": fragment,
                    "content_truncated": True,
                }
            )
            manifest_fragments.append(
                {
                    "message_id": message.id,
                    "original_chars": len(original_content),
                    "selected_chars": len(fragment),
                    "selected_tokens": fragment_tokens,
                    "decision": "truncated",
                    "reason": "context_budget",
                }
            )
            used_chars += len(fragment)
            used_tokens += fragment_tokens
            history_truncated = True
            budget_exhausted = True
            continue

        reason = (
            "token_budget_exhausted"
            if estimate_conversation_tokens(content) > remaining_tokens
            else "context_char_budget_exhausted"
        )
        manifest_fragments.append(
            {
                "message_id": message.id,
                "original_chars": len(original_content),
                "selected_chars": 0,
                "selected_tokens": 0,
                "decision": "omitted",
                "reason": reason,
            }
        )
        history_truncated = True
        budget_exhausted = True

    return {
        "version": "2.0",
        "messages": list(reversed(selected_messages)),
        "history_truncated": history_truncated,
        "context_manifest": {
            "version": "conversation-context/v2",
            "limits": {
                "max_chars": max_chars,
                "max_message_chars": max_message_chars,
                "min_fragment_chars": min_fragment_chars,
                "max_tokens": max_tokens,
                "max_messages": max_messages,
            },
            "selected_content_chars": used_chars,
            "selected_content_tokens": used_tokens,
            "fragments": list(reversed(manifest_fragments)),
        },
    }
