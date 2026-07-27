from pydantic import BaseModel
from datetime import datetime
from typing import Any

from app.schemas.final_analysis import FinalAnalysisReport


class TaskCreate(BaseModel):
    """创建任务时客户端发送的请求体"""

    question: str


class TaskOut(BaseModel):
    """服务端返回的任务信息"""

    id: int
    user_id: int
    document_id: int | None = None
    conversation_id: int | None = None
    input_message_id: int | None = None
    question: str
    status: str
    stage: str
    attempt_count: int
    celery_task_id: str | None = None
    error_type: str | None = None
    duration_ms: int | None = None
    result_summary: str | None = None
    report: FinalAnalysisReport | None = None
    result_data: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationTaskOut(BaseModel):
    """Stable task view used by the chat page while polling."""

    id: int
    conversation_id: int | None
    status: str
    stage: str
    attempt_count: int
    duration_ms: int | None
    error_type: str | None
    error_message: str | None
    result_summary: str | None
    assistant_message_id: int | None
    assistant_content: str | None
    report: FinalAnalysisReport | None
    created_at: datetime | None
    updated_at: datetime | None
