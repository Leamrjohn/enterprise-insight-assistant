import pytest
from app.core.settings import (
    DEVELOPMENT_CAPACITY_SIGNAL_TOKEN,
    EXECUTION_LEASE_SECONDS,
    MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS,
    MAX_LLM_TIMEOUT_SECONDS,
    Settings,
)
from pydantic import ValidationError


def test_input_artifact_upload_lease_seconds_accepts_a_positive_value() -> None:
    settings = Settings(input_artifact_upload_lease_seconds=120)

    assert settings.input_artifact_upload_lease_seconds == 120


def test_database_pool_timeout_requires_a_positive_bound() -> None:
    assert Settings(database_pool_timeout_seconds=5).database_pool_timeout_seconds == 5

    with pytest.raises(ValidationError):
        Settings(database_pool_timeout_seconds=0)


def test_object_storage_health_timeout_is_positive_and_bounded() -> None:
    assert (
        Settings(
            input_artifact_object_storage_health_timeout_seconds=3
        ).input_artifact_object_storage_health_timeout_seconds
        == 3
    )

    with pytest.raises(ValidationError):
        Settings(input_artifact_object_storage_health_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(input_artifact_object_storage_health_timeout_seconds=11)


def test_llm_timeout_must_leave_half_of_the_execution_lease_for_recovery() -> None:
    assert MAX_LLM_TIMEOUT_SECONDS * 2 == EXECUTION_LEASE_SECONDS
    assert Settings(llm_timeout_seconds=60).llm_timeout_seconds == 60

    with pytest.raises(ValidationError):
        Settings(llm_timeout_seconds=61)


def test_task_model_budget_settings_are_positive_and_self_consistent() -> None:
    settings = Settings(
        analysis_task_model_max_calls=4,
        analysis_task_model_max_calls_per_node=2,
        analysis_task_model_max_repairs=1,
        analysis_task_model_max_total_tokens=8000,
        analysis_task_model_max_cost="0.15",
    )

    assert str(settings.analysis_task_model_max_cost) == "0.15"
    with pytest.raises(ValidationError, match="per node"):
        Settings(
            analysis_task_model_max_calls=1,
            analysis_task_model_max_calls_per_node=2,
        )
    with pytest.raises(ValidationError, match="finite and positive"):
        Settings(analysis_task_model_max_cost="0")
    with pytest.raises(ValidationError, match="cover one model output"):
        Settings(
            llm_max_output_tokens=1024,
            analysis_task_model_max_total_tokens=1023,
        )


def test_database_pool_size_and_overflow_remain_bounded() -> None:
    settings = Settings(database_pool_size=1, database_max_overflow=0)

    assert settings.database_pool_size == 1
    assert settings.database_max_overflow == 0
    with pytest.raises(ValidationError):
        Settings(database_pool_size=0)
    with pytest.raises(ValidationError):
        Settings(database_max_overflow=-1)


def test_production_capacity_admission_rejects_the_development_token() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            jwt_secret="production-jwt-secret",
            analysis_task_capacity_admission_enabled=True,
            analysis_task_capacity_signal_url="http://capacity-signal/v1/postgres-volume",
            analysis_task_capacity_signal_token=DEVELOPMENT_CAPACITY_SIGNAL_TOKEN,
        )


def test_capacity_signal_timeout_is_positive_and_bounded() -> None:
    assert (
        Settings(
            analysis_task_capacity_signal_timeout_seconds=(
                MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS
            )
        ).analysis_task_capacity_signal_timeout_seconds
        == MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS
    )

    with pytest.raises(ValidationError):
        Settings(analysis_task_capacity_signal_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(
            analysis_task_capacity_signal_timeout_seconds=(
                MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS + 1
            )
        )


@pytest.mark.parametrize("lease_seconds", [0, -1])
def test_input_artifact_upload_lease_seconds_rejects_non_positive_values(
    lease_seconds: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings(input_artifact_upload_lease_seconds=lease_seconds)
