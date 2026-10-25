import pytest
from app.core.exceptions import TaskCapacitySignalUnavailableError
from app.core.settings import Settings
from app.modules.observability import repository


@pytest.mark.parametrize(
    "missing_field",
    ["endpoint_url", "bucket", "access_key_id", "secret_access_key"],
)
def test_object_storage_health_does_not_connect_with_incomplete_config(
    monkeypatch, missing_field
) -> None:
    settings = Settings(
        input_artifact_object_storage_endpoint_url="https://storage.invalid",
        input_artifact_object_storage_bucket="health-test",
        input_artifact_object_storage_access_key_id="test-key",
        input_artifact_object_storage_secret_access_key="test-secret",
    ).model_copy(update={f"input_artifact_object_storage_{missing_field}": None})

    def unexpected_client(*args, **kwargs):
        pytest.fail("Incomplete configuration must not create a storage client")

    monkeypatch.setattr(repository, "get_settings", lambda: settings)
    monkeypatch.setattr("boto3.client", unexpected_client)

    assert repository.check_object_storage() == "not_configured"


def test_object_storage_health_uses_bounded_configured_timeout(monkeypatch) -> None:
    settings = Settings(
        input_artifact_object_storage_endpoint_url="https://s3.us-east-1.amazonaws.com",
        input_artifact_object_storage_region="us-east-1",
        input_artifact_object_storage_bucket="agent-health-test",
        input_artifact_object_storage_access_key_id="health-test-access-key",
        input_artifact_object_storage_secret_access_key="health-test-secret-key",
        input_artifact_object_storage_health_timeout_seconds=3,
    )
    captured: dict[str, object] = {}

    class Client:
        def head_bucket(self, *, Bucket: str) -> None:
            captured["bucket"] = Bucket

    def create_client(service_name: str, **kwargs):
        captured["service_name"] = service_name
        captured["config"] = kwargs["config"]
        return Client()

    monkeypatch.setattr(repository, "get_settings", lambda: settings)
    monkeypatch.setattr("boto3.client", create_client)

    assert repository.check_object_storage() == "ok"
    assert captured["service_name"] == "s3"
    assert captured["bucket"] == settings.input_artifact_object_storage_bucket
    config = captured["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 3


def test_task_capacity_health_fails_closed_when_admission_signal_fails(
    monkeypatch,
) -> None:
    settings = Settings(
        analysis_task_capacity_admission_enabled=True,
        analysis_task_capacity_signal_url="http://capacity-signal/v1/postgres-volume",
        analysis_task_capacity_signal_token="test-capacity-token",
    )
    monkeypatch.setattr(repository, "get_settings", lambda: settings)

    def reject(_settings: Settings) -> None:
        raise TaskCapacitySignalUnavailableError(retry_after_seconds=30)

    monkeypatch.setattr(repository, "require_task_capacity", reject)

    assert repository.check_task_capacity() == "unavailable"
