from sqlalchemy.orm import Session

from app.repositories.task_repository import (
    create_task,
    get_task_by_id,
    get_tasks,
    cancel_task,
)
from app.models.analysis_task import AnalysisTask
from app.core.exceptions import TaskCannotBeCancelledError
from app.repositories.conversation_repository import (
    get_assistant_message_by_task_id,
    touch_conversation,
)


CANCELLED_MESSAGE = "本次分析已取消。"


def create_task_service(db: Session, user_id: int, question: str) -> AnalysisTask:
    """创建新任务"""
    try:
        record = create_task(db=db, user_id=user_id, question=question)
        db.commit()
        db.refresh(record)
        return record
    except Exception:
        db.rollback()
        raise


def get_task_service(db: Session, task_id: int, user_id: int) -> AnalysisTask | None:
    """根据ID查询单个任务"""
    return get_task_by_id(db=db, task_id=task_id, user_id=user_id)


def get_tasks_service(db: Session, user_id: int) -> list[AnalysisTask]:
    """查询用户的所有任务"""
    return get_tasks(db=db, user_id=user_id)


def cancel_task_service(db: Session, task_id: int, user_id: int):
    record = get_task_service(db, task_id, user_id)
    if record is None:
        return None
    if record.status not in {"queued", "running", "retrying"}:
        raise TaskCannotBeCancelledError(
            f"task {task_id} cannot be cancelled from status {record.status}"
        )
    try:
        task = cancel_task(db, record)
        assistant_message = get_assistant_message_by_task_id(db, task_id=task.id)
        if assistant_message is not None:
            assistant_message.status = "cancelled"
            assistant_message.content = CANCELLED_MESSAGE
        if task.conversation_id is not None:
            touch_conversation(db, conversation_id=task.conversation_id)
        db.commit()
        db.refresh(task)
        return task
    except Exception:
        db.rollback()
        raise
