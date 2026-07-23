from app.repositories.todo_item_repository import (
    create_todo_item,
    list_todo_items,
    get_todo_item_by_id,
    update_todo_item,
    delete_todo_item,
)
from sqlalchemy.orm import Session
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def create_todo_item_service(
    db: Session,
    user_id: int,
    title: str,
    description: str | None,
    priority: str,
    due_at: datetime | None,
):
    try:
        record = create_todo_item(db, user_id, title, description, priority, due_at)
        db.commit()
        db.refresh(record)
        return record
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to create todo item",
            extra={"user_id": user_id},
        )
        raise


def list_todo_items_service(db: Session, user_id: int, status: str | None = None):
    record = list_todo_items(db, user_id, status)
    return record


def get_todo_item_by_id_service(
    db: Session,
    item_id: int,
    user_id: int,
):
    record = get_todo_item_by_id(db, item_id, user_id)
    return record


def update_todo_item_service(
    db: Session, item_id: int, user_id: int, updates: dict[str, object]
):
    try:
        record = update_todo_item(db, item_id, user_id, updates)
        if record is None:
            return None
        db.commit()
        db.refresh(record)
        return record
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to update todo item",
            extra={"item_id": item_id, "user_id": user_id},
        )
        raise


def delete_todo_item_service(db: Session, item_id: int, user_id: int):
    try:
        record = delete_todo_item(db, item_id, user_id)
        if record is None:
            return None
        db.commit()
        return record
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to delete todo item", extra={"item_id": item_id, "user_id": user_id}
        )
        raise
