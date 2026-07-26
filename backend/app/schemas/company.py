"""HTTP contracts for tenant data-source setup."""

from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CompanyOut(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CurrentCompanyOut(BaseModel):
    user_id: int
    user_name: str
    company_id: int
    company_name: str
    role: str
    membership_status: str


class DataSourceConnectionConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=63)
    user: str = Field(min_length=1, max_length=63)
    schema_name: str = Field(
        default="public",
        alias="schema",
        serialization_alias="schema",
        min_length=1,
        max_length=63,
    )


class BusinessDataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    connection: DataSourceConnectionConfig
    credential_env_var: str = Field(min_length=1, max_length=120)

    @field_validator("credential_env_var")
    @classmethod
    def credential_reference_is_safe(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
            raise ValueError("credential_env_var must be an uppercase environment name")
        return value


class BusinessDataSourceOut(BaseModel):
    id: int
    name: str
    dialect: str
    connection: DataSourceConnectionConfig
    credential_env_var: str
    status: str
    last_error: str | None
    active_schema_snapshot_id: int | None


class AssistantDataSourceOut(BaseModel):
    """Non-sensitive data-source fields needed by the chat composer."""

    id: int
    name: str
    status: str
    active_schema_snapshot_id: int | None


class SchemaSnapshotOut(BaseModel):
    id: int
    data_source_id: int
    fingerprint: str
    catalog: dict
    discovered_by_user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyMemberOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    username: str | None
    is_active: bool
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyMemberUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(owner|admin|analyst|viewer)$")
    status: str | None = Field(default=None, pattern="^(approved|disabled|rejected)$")


class CompanyInvitationCreate(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_at: datetime | None = None


class CompanyInvitationCreated(BaseModel):
    id: int
    code: str
    max_uses: int
    expires_at: datetime | None


class MembershipApplicationRegister(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    invitation_code: str = Field(min_length=16, max_length=255)


class MembershipApplicationReapply(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    invitation_code: str = Field(min_length=16, max_length=255)


class MembershipApplicationOut(BaseModel):
    id: int
    user_id: int
    status: str
    created_at: datetime
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


class MembershipApplicationRegistered(MembershipApplicationOut):
    pass
