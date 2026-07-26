from sqlalchemy.orm import Session

from app.models.chat_record import ChatRecord


def save_chat_record(db: Session, question: str, answer: str, source: str):
    record = ChatRecord(question=question, answer=answer, source=source)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_chat_history(db: Session):
    return db.query(ChatRecord).order_by(ChatRecord.id.desc()).all()


def get_chat_record_by_id(db: Session, chat_id: int):
    return db.query(ChatRecord).filter(ChatRecord.id == chat_id).first()
