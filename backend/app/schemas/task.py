from pydantic import BaseModel
from datetime import datetime
from typing import Any


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
    result_summary: str | None = None
    result_data: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
