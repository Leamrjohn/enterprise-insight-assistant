import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicatePromptTemplateError
from app.repositories.prompt_templates_repository import (
    create_prompt_template,
    delete_prompt_template,
    get_prompt_template_by_id,
    get_prompt_templates_by_user_id,
    update_prompt_template,
)

logger = logging.getLogger(__name__)


def create_prompt_template_service(
    db: Session, user_id: int, name: str, template: str, description: str | None
):
    try:
        record = create_prompt_template(db, user_id, name, template, description)
        db.commit()
        db.refresh(record)
        return record
    except IntegrityError as e:
        db.rollback()
        logger.exception("DuplicatePromptTemplateError", extra={"erroe": str(e)})
        raise DuplicatePromptTemplateError("prompt template aleeasy exists") from e
    except Exception:
        db.rollback()
        logger.exception("Exception", extra={"user_id": user_id})
        raise


def list_prompt_templates_service(db: Session, user_id: int):
    return get_prompt_templates_by_user_id(db, user_id)


def get_prompt_template_by_id_service(db: Session, user_id: int, id: int):
    return get_prompt_template_by_id(db, user_id, id)


def update_prompt_template_service(db: Session, user_id: int, id: int, updates: dict):
    record = get_prompt_template_by_id(db, user_id, id)
    if record is None:
        return None
    try:
        record = update_prompt_template(db, record, updates)
        db.commit()
        db.refresh(record)
        return record
    except IntegrityError:
        db.rollback()
        logger.exception("DuplicatePromptTemplateError", extra={"user_id": user_id})
        raise DuplicatePromptTemplateError("failed to update prompt template ")
    except Exception:
        db.rollback()
        logger.exception("Exception", extra={"user_id": user_id})
        raise


def delete_prompt_template_service(db: Session, user_id: int, id: int):
    record = get_prompt_template_by_id(db, user_id, id)
    if record is None:
        return None
    try:
        delete_prompt_template(db, record)
        db.commit()
        return record
    except Exception:
        db.rollback()
        logger.exception("failed to delete prompt template", extra={"user_id": user_id})
        raise
