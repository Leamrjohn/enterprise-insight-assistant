from datetime import datetime
from app.models.todo_items import TodoItem
from sqlalchemy.orm import Session


def create_todo_item(
    db: Session,
    user_id: int,
    title: str,
    description: str | None,
    priority: str,
    due_at: datetime | None,
):
    record = TodoItem(
        user_id=user_id,
        title=title,
        description=description,
        priority=priority,
        due_at=due_at,
    )
    db.add(record)
    db.flush()
    return record


def list_todo_items(db: Session, user_id: int, status: str | None = None):
    query = db.query(TodoItem).filter(TodoItem.user_id == user_id)
    if status is not None:
        query = query.filter(TodoItem.status == status)

    return query.order_by(TodoItem.created_at.desc()).all()


def get_todo_item_by_id(db: Session, item_id: int, user_id: int):
    return (
        db.query(TodoItem)
        .filter(TodoItem.id == item_id, TodoItem.user_id == user_id)
        .first()
    )


def update_todo_item(
    db: Session, item_id: int, user_id: int, updates: dict[str, object]
):
    record = get_todo_item_by_id(db, item_id, user_id)
    if record is None:
        return None
    for key, values in updates.items():
        setattr(record, key, values)
    db.flush()
    return record


def delete_todo_item(db: Session, item_id: int, user_id: int):
    record = get_todo_item_by_id(db, item_id, user_id)
    if record is None:
        return None
    db.delete(record)
    db.flush()
    return record
