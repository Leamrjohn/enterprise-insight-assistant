from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated
from datetime import datetime

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DocumentMinViewRole = Annotated[str, Field(pattern="^(any|admin|owner)$")]


class DocumentCreate(BaseModel):
    name: str
    content: NonBlankStr
    source: str
    min_view_role: DocumentMinViewRole = "any"


class DocumentUpdate(BaseModel):
    name: str
    content: NonBlankStr
    source: str
    min_view_role: DocumentMinViewRole = "any"


class DocumentOut(BaseModel):
    id: int
    company_id: int | None = None
    uploaded_by_user_id: int
    name: str
    content: str | None = None
    source: str
    file_type: str | None = None
    file_size: int | None = None
    sha256: str | None = None
    status: str = "completed"
    error_message: str | None = None
    min_view_role: DocumentMinViewRole = "any"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
