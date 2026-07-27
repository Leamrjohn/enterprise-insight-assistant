from sqlalchemy.orm import Session


from app.repositories.chat_repository import (
    get_chat_history,
    save_chat_record,
    get_chat_record_by_id,
)


def get_answer_service(db: Session, question: str) -> dict:
    answer = f"你的问题是：{question}"
    source = "mock"
    save_chat_record(
        db=db,
        question=question,
        answer=answer,
        source=source,
    )

    return {"answer": answer, "source": source}


def get_chat_history_service(db: Session):
    records = get_chat_history(db)
    result = []
    for record in records:
        result.append(
            {
                "id": record.id,
                "question": record.question,
                "answer": record.answer,
                "source": record.source,
            }
        )
    return result


def get_chat_record_by_id_service(db: Session, chat_id: int):
    record = get_chat_record_by_id(db, chat_id)

    if record is None:
        return None

    return {
        "id": record.id,
        "question": record.question,
        "answer": record.answer,
        "source": record.source,
    }
