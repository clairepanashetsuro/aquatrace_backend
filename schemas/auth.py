from dataclasses import dataclass
from typing import Literal
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)
from typing_extensions import Annotated
from schemas.user import validate_password_policy


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)

    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def enforce_password_policy(cls, value: str) -> str:
        return validate_password_policy(value)


MfaCode = Annotated[
    str, StringConstraints(min_length=6, max_length=64, strip_whitespace=True)
]


class MfaVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mfa_token: str = Field(min_length=20, max_length=4096)
    code: MfaCode


class MfaSetupVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MfaDisableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=128)
    code: MfaCode


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    setup_token: str


class MfaEnabledResponse(BaseModel):
    enabled: bool
    recovery_codes: list[str] = Field(default_factory=list)


class PasswordResetCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def enforce_password_policy(cls, value: str) -> str:
        if not re.search(r"[0-9]", value) or not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError(
                "Password must include at least one number and one special character"
            )
        return value


@dataclass(frozen=True)
class LoginResult:
    access_token: str | None
    refresh_token: str | None
    mfa_required: bool
    mfa_token: str | None


class TokenResponse(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: Literal["bearer"] = "bearer"
    mfa_required: bool = False
    mfa_token: str | None = None
    mfa_setup_required: bool = False
    mfa_setup_token: str | None = None


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20, max_length=4096)
