from pydantic import BaseModel


class Requestmodel(BaseModel):
    question: str


class Requestmodel2(BaseModel):
    name: str
    content: str
    source: str
