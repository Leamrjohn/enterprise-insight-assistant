from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.task import TaskCreate, TaskOut
from app.services.task_service import (
    create_task_service,
    get_task_service,
    get_tasks_service,
)
from app.core.auth import get_current_user
from app.models.user import User
from app.tasks.analysis_tasks import process_analysis_task

router = APIRouter()


@router.post("/tasks", response_model=TaskOut)
def create_task(
    request_model: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建分析任务（异步执行）"""
    record = create_task_service(
        db=db, user_id=current_user.id, question=request_model.question
    )

    # 先提交事务，确保 Worker 能查到记录
    db.commit()
    db.refresh(record)

    # 发送异步任务给 Celery Worker
    process_analysis_task.delay(task_id=record.id, user_id=current_user.id)

    return record


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前用户的所有任务"""
    return get_tasks_service(db=db, user_id=current_user.id)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询单个任务详情"""
    record = get_task_service(db=db, task_id=task_id, user_id=current_user.id)
    if record is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="task not found")
    return record
