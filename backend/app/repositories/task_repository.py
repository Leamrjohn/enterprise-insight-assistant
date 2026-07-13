from sqlalchemy.orm import Session
from app.models.analysis_task import AnalysisTask


def create_task(db: Session, user_id: int, question: str) -> AnalysisTask:
    record = AnalysisTask(user_id=user_id, question=question, status="queued")
    db.add(record)
    db.flush()
    db.refresh(record)
    return record


def get_task_by_id(db: Session, task_id: int, user_id: int) -> AnalysisTask | None:
    return db.query(AnalysisTask).filter(
        AnalysisTask.id == task_id,
        AnalysisTask.user_id == user_id,
    ).first()


def get_tasks(db: Session, user_id: int) -> list[AnalysisTask]:
    return db.query(AnalysisTask).filter(
        AnalysisTask.user_id == user_id,
    ).order_by(AnalysisTask.id.desc()).all()
