from datetime import datetime
from pydantic import BaseModel


class ChunkOut(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    content: str
    token_count: int
    page_number: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
