from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class PromptTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    template: str = Field(min_length=1)
    description: str | None = None
    model_config = ConfigDict(str_strip_whitespace=True)


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    template: str | None = Field(default=None, min_length=1)
    description: str | None = None
    model_config = ConfigDict(str_strip_whitespace=True)


class PromptTemplateOut(BaseModel):
    id: int
    user_id: int
    name: str
    template: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
