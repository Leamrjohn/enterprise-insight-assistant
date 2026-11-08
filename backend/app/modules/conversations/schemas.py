"""Public request and response contracts for conversations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MessageRole = Literal["user", "assistant"]
MessageStatus = Literal[
    "queued",
    "running",
    "completed",
    "partial",
    "failed",
    "cancelled",
    "needs_clarification",
]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    data_source_id: int | None = Field(default=None, gt=0)


class ConversationMessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1)
    document_ids: list[int] | None = None
    artifact_version_ids: list[int] = Field(default_factory=list, max_length=20)

    @field_validator("artifact_version_ids")
    @classmethod
    def validate_artifact_version_ids(cls, value: list[int]) -> list[int]:
        if any(
            isinstance(version_id, bool)
            or not isinstance(version_id, int)
            or version_id <= 0
            for version_id in value
        ):
            raise ValueError("artifact_version_ids must contain positive integers")
        if len(set(value)) != len(value):
            raise ValueError("artifact_version_ids must not contain duplicates")
        return value


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str | None
    company_id: int | None
    data_source_id: int | None
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


class ConversationTaskRetryAccepted(BaseModel):
    task_id: int
    status: Literal["queued"]
    assistant_message: ConversationMessageOut
