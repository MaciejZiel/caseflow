"""Schemas for organization invitations and membership management."""

from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.v1.schemas.auth import (
    MembershipResponse,
    OrganizationResponse,
    UserResponse,
    validate_password_rules,
)
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
        return validate_password_rules(value)


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


class OrganizationContextResponse(BaseModel):
    organization: OrganizationResponse
    membership: MembershipResponse


class OrganizationMemberResponse(MembershipResponse):
    user: UserResponse


class OrganizationMemberUpdateRequest(BaseModel):
    role: OrganizationRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> OrganizationMemberUpdateRequest:
        if self.role is None and self.is_active is None:
            msg = "Provide at least one field to update."
            raise ValueError(msg)
        return self
