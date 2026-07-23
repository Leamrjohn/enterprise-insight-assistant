from sqlalchemy.orm import Session
from app.models.labels import Label


def create_label(db: Session, user_id: int, label_name: str, color: str):
    created_label = Label(user_id=user_id, name=label_name, color=color)
    db.add(created_label)
    db.flush()
    return created_label


def list_labels_by_user(db: Session, user_id: int):
    record = db.query(Label).filter(Label.user_id == user_id)
    record = record.order_by(Label.created_at.desc()).all()
    return record


def get_label_by_id_and_user(db: Session, label_id: int, user_id: int):
    record = (
        db.query(Label).filter(Label.id == label_id, Label.user_id == user_id).first()
    )
    if record is None:
        return None
    return record


def get_label_by_name_and_user(db: Session, name: str, user_id: int):
    return db.query(Label).filter(Label.name == name, Label.user_id == user_id).first()


def update_label(db: Session, label: Label, updates: dict):
    for key, value in updates.items():
        setattr(label, key, value)
    db.flush()
    return label


def delete_label(
    db: Session,
    label: Label,
):
    db.delete(label)
    db.flush()
