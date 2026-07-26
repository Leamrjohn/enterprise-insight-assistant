from celery import Celery

from app.core.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "agent_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
)


celery_app.conf.update(
    task_default_queue="test" if settings.app_env == "test" else "celery",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    imports=[
        "app.tasks.analysis_tasks",
        "app.tasks.document_tasks",
        "app.tasks.outbox_tasks",
    ],
    beat_schedule={
        "publish-pending-analysis-task-events": {
            "task": "app.tasks.outbox_tasks.publish_pending_analysis_task_events",
            "schedule": 5.0,
        }
    },
)
