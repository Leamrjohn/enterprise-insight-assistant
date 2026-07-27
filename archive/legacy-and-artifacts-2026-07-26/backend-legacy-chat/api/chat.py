from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.request import Requestmodel
from app.schemas.response import ChatHistoryItem, Responsemodel
from app.services.chat_service import (
    get_answer_service,
    get_chat_history_service,
    get_chat_record_by_id_service,
)

router = APIRouter()


@router.post("/chat", response_model=Responsemodel)
def ask_chat(
    request_model: Requestmodel,
    db: Session = Depends(get_db),
):
    return get_answer_service(db, request_model.question)


@router.get("/chat/history", response_model=list[ChatHistoryItem])
def get_chat_history(
    db: Session = Depends(get_db),
):
    return get_chat_history_service(db)


@router.get("/chat/history/{chat_id}", response_model=ChatHistoryItem)
def get_chat_record_by_id(chat_id: int, db: Session = Depends(get_db)):
    record = get_chat_record_by_id_service(db, chat_id)

    if record is None:
        raise HTTPException(status_code=404, detail="chat record not found")
    return record
