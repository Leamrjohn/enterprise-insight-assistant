from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str | None = None
    redis: str | None = None
    object_storage: str | None = None
    task_capacity: str | None = None
