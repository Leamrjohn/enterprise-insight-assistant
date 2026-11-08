"""HTTP contracts for tenant data-source setup."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class BusinessDataSourceCreate(BaseModel):
    """A11b: admins pick one of their company's platform-registered connections."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    connection_id: int = Field(gt=0)


class DataConnectionOut(BaseModel):
    """What a company admin may know about a platform connection: not its address."""

    id: int
    name: str
    status: str


class BusinessDataSourceOut(BaseModel):
    id: int
    name: str
    dialect: str
    connection_id: int | None
    connection_name: str | None
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


class CompanyMemberPasswordReset(BaseModel):
    """Owner-authorized password replacement; the old password is never exposed."""

    new_password: str = Field(min_length=8, max_length=128)


class CompanyInvitationCreate(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_at: datetime | None = None


class CompanyInvitationCreated(BaseModel):
    id: int
    code: str
    max_uses: int
    expires_at: datetime | None


class CompanyInvitationOut(BaseModel):
    id: int
    max_uses: int
    used_count: int
    is_active: bool
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


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
    user_name: str | None = None
    username: str | None = None

    model_config = {"from_attributes": True}


class MembershipApplicationRegistered(MembershipApplicationOut):
    pass
