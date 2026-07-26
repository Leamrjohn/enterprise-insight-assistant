from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.company_auth import CurrentCompanyContext, get_current_company_context
from app.db.session import get_db
from app.schemas.todo_items import TodoItemCreate, TodoItemOut, TodoItemUpdate
from app.services.todo_item_service import (
    create_todo_item_service,
    list_todo_items_service,
    get_todo_item_by_id_service,
    update_todo_item_service,
    delete_todo_item_service,
)
from typing import Literal

router = APIRouter()


@router.post(
    "/todo-items",
    response_model=TodoItemOut,
    status_code=201,
)
def create_todo_task(
    request_model: TodoItemCreate,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    return create_todo_item_service(
        db=db,
        user_id=context.user.id,
        title=request_model.title,
        description=request_model.description,
        priority=request_model.priority,
        due_at=request_model.due_at,
    )


@router.get("/todo-items", response_model=list[TodoItemOut])
def list_todo_items(
    status: Literal["todo", "in_progress", "done"] | None = None,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    record = list_todo_items_service(db=db, user_id=context.user.id, status=status)
    return record


@router.get("/todo-items/{item_id}", response_model=TodoItemOut)
def get_todo_item_by_id(
    item_id: int,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    record = get_todo_item_by_id_service(
        db=db,
        item_id=item_id,
        user_id=context.user.id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="todo item not found")
    else:
        return record


@router.patch("/todo-items/{item_id}", response_model=TodoItemOut)
def update_todo_item(
    item_id: int,
    request_model: TodoItemUpdate,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    updates = request_model.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=422, detail="at least one field must be provided"
        )
    record = update_todo_item_service(db, item_id, context.user.id, updates)
    if record is None:
        raise HTTPException(status_code=404, detail="todo item not found")
    return record


@router.delete("/todo-items/{item_id}", status_code=204)
def delete_todo_item(
    item_id: int,
    db: Session = Depends(get_db),
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    record = delete_todo_item_service(db, item_id, context.user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="todo item not found")
