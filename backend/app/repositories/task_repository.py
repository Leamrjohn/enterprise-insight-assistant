from sqlalchemy.orm import Session
from app.models.analysis_task import AnalysisTask


def create_task(
    db: Session,
    user_id: int,
    question: str,
    *,
    conversation_id: int | None = None,
    input_message_id: int | None = None,
    context_snapshot: dict | None = None,
) -> AnalysisTask:
    record = AnalysisTask(
        user_id=user_id,
        question=question,
        status="queued",
        conversation_id=conversation_id,
        input_message_id=input_message_id,
        context_snapshot=context_snapshot,
    )
    db.add(record)
    db.flush()
    db.refresh(record)
    return record


def get_task_by_id(db: Session, task_id: int, user_id: int) -> AnalysisTask | None:
    return (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.id == task_id,
            AnalysisTask.user_id == user_id,
        )
        .first()
    )


def get_tasks(db: Session, user_id: int) -> list[AnalysisTask]:
    return (
        db.query(AnalysisTask)
        .filter(
            AnalysisTask.user_id == user_id,
        )
        .order_by(AnalysisTask.id.desc())
        .all()
    )


def cancel_task(db: Session, task: AnalysisTask):
    task.status = "cancelled"
    db.flush()
    return task
