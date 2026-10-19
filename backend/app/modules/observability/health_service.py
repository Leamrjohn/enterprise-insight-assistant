from app.modules.observability.repository import (
    check_database,
    check_object_storage,
    check_redis,
    check_task_capacity,
)
from sqlalchemy.orm import Session


def get_readiness_service(db: Session) -> dict[str, str]:
    if not check_database(db):
        return {
            "status": "unavailable",
            "database": "unavailable",
            "redis": "unknown",
            "object_storage": "unknown",
            "task_capacity": "unknown",
        }
    if not check_redis():
        return {
            "status": "unavailable",
            "database": "ok",
            "redis": "unavailable",
            "object_storage": "unknown",
            "task_capacity": "unknown",
        }
    object_storage = check_object_storage()
    if object_storage == "unavailable":
        return {
            "status": "unavailable",
            "database": "ok",
            "redis": "ok",
            "object_storage": "unavailable",
            "task_capacity": "unknown",
        }

    task_capacity = check_task_capacity()
    if task_capacity == "unavailable":
        return {
            "status": "unavailable",
            "database": "ok",
            "redis": "ok",
            "object_storage": object_storage,
            "task_capacity": "unavailable",
        }

    return {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
        "object_storage": object_storage,
        "task_capacity": task_capacity,
    }
