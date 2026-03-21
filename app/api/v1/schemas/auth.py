"""Schemas for authentication and current session endpoints."""

from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.organizations.models import OrganizationRole, OrganizationStatus


def _normalize_email(value: str) -> str:
    _, parsed = parseaddr(value)
    email = parsed.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        msg = "Provide a valid email address."
        raise ValueError(msg)
    return email


class RegistrationRequest(BaseModel):
    organization_name: str = Field(min_length=3, max_length=255)
    organization_slug: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        has_upper = any(character.isupper() for character in value)
        has_lower = any(character.islower() for character in value)
        has_digit = any(character.isdigit() for character in value)
        if not (has_upper and has_lower and has_digit):
            msg = "Password must contain upper-case, lower-case and numeric characters."
            raise ValueError(msg)
        return value


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)
    organization_slug: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str
    last_name: str
    is_active: bool
    created_at: datetime


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    status: OrganizationStatus
    created_at: datetime


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: OrganizationRole
    is_active: bool
    joined_at: datetime


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserResponse
    organization: OrganizationResponse
    membership: MembershipResponse


class AuthResponse(SessionResponse):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
