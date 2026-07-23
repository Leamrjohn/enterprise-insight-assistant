from sqlalchemy.orm import Session
from app.models.prompt_templates import PromptTemplate


def create_prompt_template(
    db: Session, user_id: int, name: str, template: str, description: str | None
):
    prompt_template = PromptTemplate(
        user_id=user_id, name=name, template=template, description=description
    )
    db.add(prompt_template)
    db.flush()
    return prompt_template


def get_prompt_templates_by_user_id(db: Session, user_id: int):
    record = db.query(PromptTemplate).filter(PromptTemplate.user_id == user_id)
    record = record.order_by(PromptTemplate.created_at.desc()).all()
    return record


def get_prompt_template_by_id(db: Session, user_id: int, id: int):
    return (
        db.query(PromptTemplate)
        .filter(PromptTemplate.user_id == user_id, PromptTemplate.id == id)
        .first()
    )


def update_prompt_template(db: Session, prompt_template: PromptTemplate, updates: dict):
    for key, value in updates.items():
        setattr(prompt_template, key, value)
    db.flush()
    return prompt_template


def delete_prompt_template(db: Session, prompt_template: PromptTemplate):
    db.delete(prompt_template)
    db.flush()
