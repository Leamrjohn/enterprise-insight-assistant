from app.core.exceptions import TaskCapacityAdmissionError
from app.core.settings import get_settings
from app.modules.workflow.lifecycle.capacity import require_task_capacity
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.orm import Session


def check_database(db: Session) -> bool:
    return db.execute(text("SELECT 1")).scalar_one() == 1


def check_redis() -> bool:
    client = Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        return bool(client.ping())
    except RedisError:
        return False
    finally:
        client.close()


def check_object_storage() -> str:
    settings = get_settings()
    if (
        not settings.input_artifact_object_storage_endpoint_url
        or not settings.input_artifact_object_storage_bucket
        or not settings.input_artifact_object_storage_access_key_id
        or not settings.input_artifact_object_storage_secret_access_key
    ):
        return "not_configured"
    try:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.input_artifact_object_storage_endpoint_url,
            region_name=settings.input_artifact_object_storage_region,
            aws_access_key_id=(
                settings.input_artifact_object_storage_access_key_id.get_secret_value()
            ),
            aws_secret_access_key=(
                settings.input_artifact_object_storage_secret_access_key.get_secret_value()
            ),
            config=Config(
                connect_timeout=settings.input_artifact_object_storage_health_timeout_seconds,
                read_timeout=settings.input_artifact_object_storage_health_timeout_seconds,
                retries={"max_attempts": 0},
            ),
        )
        client.head_bucket(Bucket=settings.input_artifact_object_storage_bucket)
    except (BotoCoreError, ClientError):
        return "unavailable"
    return "ok"


def check_task_capacity() -> str:
    """Report whether new analysis-task admission is currently possible."""
    settings = get_settings()
    if not settings.analysis_task_capacity_admission_enabled:
        return "not_configured"
    try:
        require_task_capacity(settings)
    except TaskCapacityAdmissionError:
        return "unavailable"
    return "ok"
