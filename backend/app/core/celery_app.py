from celery import Celery
from celery.schedules import crontab
from celery.signals import beat_init, celeryd_init, setup_logging

from app.core.heartbeat import WorkerHeartbeat
from app.core.logging import configure_logging
from app.core.settings import get_settings
from app.core.tracing import setup_tracing

settings = get_settings()


@celeryd_init.connect
@beat_init.connect
def _setup_celery_tracing(**_kwargs) -> None:
    """Only Celery processes are agent-celery; the API imports this module too."""
    setup_tracing("agent-celery")


@setup_logging.connect
def _use_project_logging(**_kwargs) -> None:
    """Replace Celery's plain-text root handler with redacted JSON logging."""
    configure_logging(settings)


celery_app = Celery(
    "agent_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
# O4: the worker touches its heartbeat file from its own event loop.
if celery_app.steps is None:  # set by Celery.__init__; typed as optional
    raise RuntimeError("Celery app has no bootstep registry")
celery_app.steps["worker"].add(WorkerHeartbeat)


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
        "app.modules.workflow.tasks",
        "app.modules.documents.tasks",
        "app.modules.workflow.outbox_tasks",
        "app.modules.input_artifacts.tasks",
        "app.modules.input_artifacts.outbox_tasks",
        "app.modules.memory.tasks",
    ],
    beat_schedule={
        "publish-pending-analysis-task-events": {
            "task": "app.modules.workflow.outbox_tasks.publish_pending_analysis_task_events",
            "schedule": 5.0,
        },
        "recover-expired-analysis-executions": {
            "task": "app.modules.workflow.outbox_tasks.recover_expired_analysis_executions",
            "schedule": 10.0,
        },
        "reconcile-stranded-analysis-tasks": {
            "task": "app.modules.workflow.outbox_tasks.reconcile_stranded_analysis_tasks",
            "schedule": 60.0,
        },
        "cleanup-expired-memories": {
            "task": "app.modules.memory.tasks.cleanup_expired_memories",
            # A clock time: an interval would restart whenever beat restarts.
            "schedule": crontab(hour=3, minute=0),
        },
        "publish-pending-artifact-processing-events": {
            "task": "app.modules.input_artifacts.outbox_tasks.publish_pending_artifact_processing_events",
            "schedule": 5.0,
        },
    },
)
