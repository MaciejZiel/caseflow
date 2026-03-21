"""Schemas for organization invitations and membership management."""

from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.organizations.models import OrganizationRole


def _normalize_email(value: str) -> str:
    _, parsed = parseaddr(value)
    email = parsed.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        msg = "Provide a valid email address."
        raise ValueError(msg)
    return email


class InvitationCreateRequest(BaseModel):
    email: str
    role: OrganizationRole

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=128)

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


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: OrganizationRole
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InvitationCreateResponse(BaseModel):
    invitation: InvitationResponse
    invitation_token: str
