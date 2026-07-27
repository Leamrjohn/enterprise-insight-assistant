from pydantic import BaseModel


class Responsemodel(BaseModel):
    answer: str
    source: str


class ChatHistoryItem(BaseModel):
    id: int
    question: str
    answer: str
    source: str


class DocumentModel(BaseModel):
    id: int
    name: str
    content: str
    source: str
