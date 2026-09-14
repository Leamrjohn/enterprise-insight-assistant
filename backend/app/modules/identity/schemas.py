from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class UserOut(BaseModel):
    id: int
    name: str
    username: str | None = None
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CurrentUserOut(UserOut):
    """The only post-login identity payload needed by the client."""

    company_id: int
    company_name: str
    membership_status: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class AccessTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class InitialPasswordSetup(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class OwnerBootstrapRequest(LoginRequest):
    name: str = Field(min_length=1, max_length=255)
    company_name: str = Field(min_length=1, max_length=255)
