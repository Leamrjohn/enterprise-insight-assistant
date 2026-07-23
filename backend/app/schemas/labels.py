from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

Color = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class LabelCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=50)
    color: Color = "#3B82F6"


class LabelUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=50)
    color: Color | None = None


class LabelOut(BaseModel):
    id: int
    user_id: int
    name: str
    color: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
