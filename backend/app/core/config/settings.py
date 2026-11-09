"""``Settings`` combines every configuration domain (K1).

All domains share one ``backend/.env`` and the process environment; variable
names are the field names in upper case, unchanged from the flat settings.
Checks that span domains live here; each domain validates its own fields.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from dotenv import dotenv_values
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

from app.core.config.admission import (
    DEVELOPMENT_CAPACITY_SIGNAL_TOKEN,
    AdmissionConfig,
)
from app.core.config.app import AppConfig
from app.core.config.artifacts import ArtifactConfig
from app.core.config.base import BACKEND_DIR, ConfigDomain
from app.core.config.context import ContextConfig
from app.core.config.flags import FeatureFlags
from app.core.config.infra import InfraConfig
from app.core.config.memory import MemoryConfig
from app.core.config.model import ModelConfig
from app.core.config.rag import RagConfig
from app.core.config.security import DEVELOPMENT_JWT_SECRET, SecurityConfig
from app.core.config.tool import ToolConfig

DOMAINS: tuple[type[ConfigDomain], ...] = (
    AppConfig,
    InfraConfig,
    SecurityConfig,
    AdmissionConfig,
    ModelConfig,
    ToolConfig,
    ContextConfig,
    MemoryConfig,
    RagConfig,
    FeatureFlags,
    ArtifactConfig,
)

DomainT = TypeVar("DomainT", bound=ConfigDomain)
logger = logging.getLogger(__name__)


class Settings(
    AppConfig,
    InfraConfig,
    SecurityConfig,
    AdmissionConfig,
    ModelConfig,
    ToolConfig,
    ContextConfig,
    MemoryConfig,
    RagConfig,
    FeatureFlags,
    ArtifactConfig,
    BaseSettings,
):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_customise_sources",),
    )

    def domain(self, domain: type[DomainT]) -> DomainT:
        """One domain's effective values, e.g. ``settings.domain(RagConfig)``."""
        values = {name: getattr(self, name) for name in domain.model_fields}
        return domain.model_construct(**values)

    @model_validator(mode="after")
    def validate_database_password(self) -> Self:
        if not self.database_password.get_secret_value():
            raise ValueError("DATABASE_PASSWORD must not be empty")

        if not self.business_database_password.get_secret_value():
            raise ValueError("BUSINESS_DATABASE_PASSWORD must not be empty")
        if (
            self.app_env == "production"
            and self.jwt_secret.get_secret_value() == DEVELOPMENT_JWT_SECRET
        ):
            raise ValueError("JWT_SECRET must be configured in production")

        object_storage_values = (
            self.input_artifact_object_storage_endpoint_url,
            self.input_artifact_object_storage_bucket,
            (
                self.input_artifact_object_storage_access_key_id.get_secret_value()
                if self.input_artifact_object_storage_access_key_id is not None
                else None
            ),
            (
                self.input_artifact_object_storage_secret_access_key.get_secret_value()
                if self.input_artifact_object_storage_secret_access_key is not None
                else None
            ),
        )
        if any(value is not None for value in object_storage_values) and not all(
            isinstance(value, str) and value.strip() for value in object_storage_values
        ):
            raise ValueError(
                "input artifact object storage settings must be configured together"
            )
        if self.analysis_task_capacity_admission_enabled and not all(
            (
                self.analysis_task_capacity_signal_url,
                self.analysis_task_capacity_signal_token is not None
                and self.analysis_task_capacity_signal_token.get_secret_value(),
            )
        ):
            raise ValueError(
                "capacity admission requires a signal URL and shared token"
            )
        if (
            self.app_env == "production"
            and self.analysis_task_capacity_admission_enabled
            and self.analysis_task_capacity_signal_token is not None
            and self.analysis_task_capacity_signal_token.get_secret_value()
            == DEVELOPMENT_CAPACITY_SIGNAL_TOKEN
        ):
            raise ValueError(
                "ANALYSIS_TASK_CAPACITY_SIGNAL_TOKEN must be configured in production"
            )
        if (
            self.analysis_task_model_max_calls_per_node
            > self.analysis_task_model_max_calls
        ):
            raise ValueError(
                "analysis task model calls per node must not exceed total calls"
            )
        if self.analysis_task_model_max_repairs > self.analysis_task_model_max_calls:
            raise ValueError("analysis task model repairs must not exceed total calls")
        if self.analysis_task_model_max_total_tokens < self.llm_max_output_tokens:
            raise ValueError(
                "analysis task total model tokens must cover one model output"
            )
        return self


def check_known_keys(
    settings: Settings,
    *,
    env_file: Path = BACKEND_DIR / ".env",
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """K2: refuse (production) or warn about names no setting declares.

    Only names are reported, never values.
    """
    from app.core.config.catalog import unknown_keys

    env_keys = list(dotenv_values(env_file)) if env_file.is_file() else []
    unknown = unknown_keys(
        env_keys,
        os.environ if environ is None else environ,
        credential_names=settings.data_source_credential_env_allowlist,
    )
    if unknown:
        message = "Unknown configuration keys (misspelt or removed): " + ", ".join(
            unknown
        )
        if settings.app_env == "production":
            raise ValueError(message)
        logger.warning(message)
    return unknown


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    check_known_keys(settings)
    return settings
