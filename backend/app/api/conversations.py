"""Conversation HTTP API."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.company_auth import (
    CurrentCompanyContext,
    get_current_company_context,
    require_analysis_permission,
)
from app.db.session import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationMessageAccepted,
    ConversationMessageCreate,
    ConversationMessageOut,
    ConversationOut,
    ConversationTaskRetryAccepted,
)
from app.schemas.task import ConversationTaskOut, TaskOut
from app.repositories.conversation_repository import get_assistant_message_by_task_id
from app.services.conversation_service import (
    ConversationDocumentScopeError,
    DataSourceNotReadyError,
    cancel_conversation_task_service,
    create_conversation_service,
    create_conversation_task_service,
    get_conversation_messages_service,
    get_conversation_service,
    get_conversation_task_service,
    get_conversations_service,
    retry_conversation_task_service,
)
from app.services.outbox_service import publish_analysis_task_event


router = APIRouter()


def _conversation_task_out(db: Session, task) -> ConversationTaskOut:
    assistant_message = get_assistant_message_by_task_id(db, task_id=task.id)
    return ConversationTaskOut(
        id=task.id,
        conversation_id=task.conversation_id,
        status=task.status,
        stage=task.stage,
        attempt_count=task.attempt_count,
        duration_ms=task.duration_ms,
        error_type=task.error_type,
        error_message=task.error_message,
        result_summary=task.result_summary,
        assistant_message_id=assistant_message.id if assistant_message else None,
        assistant_content=assistant_message.content if assistant_message else None,
        report=task.report,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_endpoint(
    request_model: ConversationCreate,
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
):
    try:
        return create_conversation_service(
            db,
            context=context,
            title=request_model.title,
            data_source_id=request_model.data_source_id,
        )
    except DataSourceNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (PermissionError, ValueError):
        raise HTTPException(status_code=404, detail="company or data source not found")


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations_endpoint(
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    return get_conversations_service(db, context=context)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation_endpoint(
    conversation_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessageOut],
)
def list_conversation_messages_endpoint(
    conversation_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    messages = get_conversation_messages_service(
        db,
        conversation_id=conversation_id,
        context=context,
    )
    if messages is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return messages


@router.get(
    "/conversations/{conversation_id}/tasks/{task_id}",
    response_model=ConversationTaskOut,
)
def get_conversation_task_endpoint(
    conversation_id: int,
    task_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    task = get_conversation_task_service(
        db,
        conversation_id=conversation_id,
        task_id=task_id,
        context=context,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _conversation_task_out(db, task)


@router.post(
    "/conversations/{conversation_id}/tasks/{task_id}/cancel",
    response_model=TaskOut,
)
def cancel_conversation_task_endpoint(
    conversation_id: int,
    task_id: int,
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    try:
        task = cancel_conversation_task_service(
            db,
            conversation_id=conversation_id,
            task_id=task_id,
            context=context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post(
    "/conversations/{conversation_id}/tasks/{task_id}/retry",
    response_model=ConversationTaskRetryAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_conversation_task_endpoint(
    conversation_id: int,
    task_id: int,
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
):
    try:
        bundle = retry_conversation_task_service(
            db,
            conversation_id=conversation_id,
            task_id=task_id,
            context=context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if bundle is None:
        raise HTTPException(status_code=404, detail="task not found")

    publish_analysis_task_event(db, event_id=bundle.outbox_event_id)
    return ConversationTaskRetryAccepted(
        task_id=bundle.task.id,
        status="queued",
        assistant_message=ConversationMessageOut.model_validate(
            bundle.assistant_message
        ),
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationMessageAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_conversation_message_endpoint(
    conversation_id: int,
    request_model: ConversationMessageCreate,
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
):
    try:
        bundle = create_conversation_task_service(
            db,
            conversation_id=conversation_id,
            context=context,
            content=request_model.content,
            document_ids=request_model.document_ids,
        )
    except ConversationDocumentScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DataSourceNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if bundle is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    publish_analysis_task_event(db, event_id=bundle.outbox_event_id)

    return ConversationMessageAccepted(
        task_id=bundle.task.id,
        status="queued",
        user_message=ConversationMessageOut.model_validate(bundle.user_message),
        assistant_message=ConversationMessageOut.model_validate(
            bundle.assistant_message
        ),
    )
