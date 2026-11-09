"""Authentication, request rate limits and data-source egress rules."""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator

from app.core.config.base import ConfigDomain, require_positive

DEVELOPMENT_JWT_SECRET = "development-only-change-before-production"


class SecurityConfig(ConfigDomain):
    jwt_secret: SecretStr = SecretStr(DEVELOPMENT_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    # Requests one client may send per sliding window (core/middleware.py).
    rate_limit_max_requests: int = 100
    rate_limit_window_seconds: int = 60
    # Tenant data sources may read only these credential names and never reach these hosts.
    data_source_credential_env_allowlist: list[str] = Field(
        default_factory=lambda: [
            "ACME_DEMO_DATABASE_PASSWORD",
            "BETA_DEMO_DATABASE_PASSWORD",
        ]
    )
    data_source_blocked_hosts: list[str] = Field(
        default_factory=lambda: [
            "postgres",
            "redis",
            "api",
            "worker",
            "report-worker",
            "beat",
            "frontend",
            "clamd",
            "localstack",
            "capacity-signal",
            "localhost",
        ]
    )

    @field_validator("rate_limit_max_requests", "rate_limit_window_seconds")
    @classmethod
    def security_validate_positive_int(cls, value: int) -> int:
        return require_positive(value)
