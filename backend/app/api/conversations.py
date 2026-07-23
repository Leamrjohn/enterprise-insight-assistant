"""Conversation HTTP API."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationMessageAccepted,
    ConversationMessageCreate,
    ConversationMessageOut,
    ConversationOut,
)
from app.services.conversation_service import (
    compensate_enqueue_failure_service,
    create_conversation_service,
    create_conversation_task_service,
    get_conversation_messages_service,
    get_conversation_service,
    get_conversations_service,
)
from app.tasks.analysis_tasks import process_analysis_task


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_endpoint(
    request_model: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_conversation_service(
        db,
        user_id=current_user.id,
        title=request_model.title,
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_conversations_service(db, user_id=current_user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation_endpoint(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = get_conversation_service(
        db,
        conversation_id=conversation_id,
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    messages = get_conversation_messages_service(
        db,
        conversation_id=conversation_id,
        user_id=current_user.id,
    )
    if messages is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return messages


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationMessageAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_conversation_message_endpoint(
    conversation_id: int,
    request_model: ConversationMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bundle = create_conversation_task_service(
        db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        content=request_model.content,
    )
    if bundle is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    try:
        process_analysis_task.delay(task_id=bundle.task.id)
    except Exception:
        logger.exception(
            "Failed to enqueue conversation analysis task",
            extra={
                "task_id": bundle.task.id,
                "user_id": current_user.id,
                "conversation_id": conversation_id,
            },
        )
        compensate_enqueue_failure_service(
            db,
            task_id=bundle.task.id,
            user_id=current_user.id,
        )
        raise HTTPException(
            status_code=503,
            detail="analysis task could not be queued",
        )

    return ConversationMessageAccepted(
        task_id=bundle.task.id,
        status="queued",
        user_message=ConversationMessageOut.model_validate(bundle.user_message),
        assistant_message=ConversationMessageOut.model_validate(
            bundle.assistant_message
        ),
    )
