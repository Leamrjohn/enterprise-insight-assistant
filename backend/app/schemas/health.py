from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str | None = None
