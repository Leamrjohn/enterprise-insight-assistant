from app.repositories.label_repository import (
    create_label,
    list_labels_by_user,
    get_label_by_id_and_user,
    get_label_by_name_and_user,
    update_label,
    delete_label,
)
from sqlalchemy.orm import Session
from app.core.exceptions import DuplicateLabelError
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)


def create_label_service(db: Session, user_id: int, label_name: str, color: str):
    result = get_label_by_name_and_user(db=db, user_id=user_id, name=label_name)
    if result:
        raise DuplicateLabelError
    try:
        record = create_label(db, user_id, label_name, color)
        db.commit()
        db.refresh(record)
        return record
    except IntegrityError as exc:
        db.rollback()
        logger.exception("data UniqueConstraint", extra={"user_id": user_id})
        raise DuplicateLabelError("label name already exists") from exc
    except Exception as e:
        db.rollback()
        logger.exception("Exception", extra={"Exception": str(e)})
        raise


def list_labels_service(
    db: Session,
    user_id: int,
):
    record = list_labels_by_user(db, user_id)
    return record


def get_label_by_id_service(db: Session, label_id: int, user_id: int):
    record = get_label_by_id_and_user(db, label_id, user_id)
    return record


def update_label_service(db: Session, label_id: int, user_id: int, updates: dict):
    result = get_label_by_id_and_user(db, label_id, user_id)
    if result is None:
        return None
    if "name" in updates:
        same_name_label = get_label_by_name_and_user(db, updates["name"], user_id)
        if same_name_label is not None and same_name_label.id != result.id:
            raise DuplicateLabelError
    try:
        result = update_label(db, result, updates)
        db.commit()
        db.refresh(result)
        return result
    except IntegrityError:
        db.rollback()
        logger.exception("data UniqueConstraint", extra={"user_id": user_id})
        raise DuplicateLabelError
    except Exception as e:
        db.rollback()
        logger.exception("Exception", extra={"Exception": str(e)})
        raise


def delete_label_service(
    db: Session,
    label_id: int,
    user_id: int,
):
    record = get_label_by_id_and_user(db, label_id, user_id)
    if record is None:
        return None
    try:
        delete_label(
            db,
            record,
        )
        db.commit()
        return record
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to delete label",
            extra={"label_id": label_id, "user_id": user_id},
        )
        raise
