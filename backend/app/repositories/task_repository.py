from sqlalchemy.orm import Session
from app.models.analysis_task import AnalysisTask, AnalysisTaskDocument


def create_task(
    db: Session,
    user_id: int,
    question: str,
    *,
    conversation_id: int | None = None,
    input_message_id: int | None = None,
    context_snapshot: dict | None = None,
    company_id: int | None = None,
    data_source_id: int | None = None,
    schema_snapshot_id: int | None = None,
    document_ids: list[int] | None = None,
    parent_task_id: int | None = None,
    request_id: str | None = None,
) -> AnalysisTask:
    record = AnalysisTask(
        user_id=user_id,
        question=question,
        status="queued",
        conversation_id=conversation_id,
        input_message_id=input_message_id,
        context_snapshot=context_snapshot,
        company_id=company_id,
        data_source_id=data_source_id,
        schema_snapshot_id=schema_snapshot_id,
        parent_task_id=parent_task_id,
        request_id=request_id,
    )
    db.add(record)
    db.flush()
    for document_id in document_ids or []:
        db.add(AnalysisTaskDocument(task_id=record.id, document_id=document_id))
    db.refresh(record)
    return record


def get_task_document_ids(db: Session, *, task_id: int) -> list[int]:
    return [
        document_id
        for (document_id,) in (
            db.query(AnalysisTaskDocument.document_id)
            .filter(AnalysisTaskDocument.task_id == task_id)
            .order_by(AnalysisTaskDocument.document_id)
            .all()
        )
    ]


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
