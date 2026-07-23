"""Public request and response contracts for conversations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MessageRole = Literal["user", "assistant"]
MessageStatus = Literal[
    "queued",
    "running",
    "completed",
    "partial",
    "failed",
    "cancelled",
]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)


class ConversationMessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: MessageRole
    content: str | None
    status: MessageStatus
    analysis_task_id: int | None
    created_at: datetime
    updated_at: datetime


class ConversationMessageAccepted(BaseModel):
    task_id: int
    status: Literal["queued"]
    user_message: ConversationMessageOut
    assistant_message: ConversationMessageOut
