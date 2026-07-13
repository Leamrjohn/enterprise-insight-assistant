from sqlalchemy.orm import Session

from app.repositories.task_repository import create_task, get_task_by_id, get_tasks
from app.models.analysis_task import AnalysisTask


def create_task_service(
    db: Session, user_id: int, question: str
) -> AnalysisTask:
    """创建新任务"""
    return create_task(db=db, user_id=user_id, question=question)


def get_task_service(
    db: Session, task_id: int, user_id: int
) -> AnalysisTask | None:
    """根据ID查询单个任务"""
    return get_task_by_id(db=db, task_id=task_id, user_id=user_id)


def get_tasks_service(db: Session, user_id: int) -> list[AnalysisTask]:
    """查询用户的所有任务"""
    return get_tasks(db=db, user_id=user_id)
