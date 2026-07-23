from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Literal


class TodoItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    due_at: datetime | None = None


class TodoItemOut(BaseModel):
    id: int
    user_id: int
    title: str
    description: str | None
    status: str
    priority: str
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TodoItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: Literal["todo", "in_progress", "done"] | None = None
    priority: Literal["low", "medium", "high"] | None = None
    due_at: datetime | None = None

    model_config = ConfigDict(str_strip_whitespace=True)
