from app.core.celery_app import celery_app
from app.core.settings import get_settings


def test_test_environment_routes_default_tasks_to_test_queue() -> None:
    assert get_settings().app_env == "test"
    assert celery_app.conf.task_default_queue == "test"
