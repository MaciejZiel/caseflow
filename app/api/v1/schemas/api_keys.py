"""Schemas for API key management and integration access."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.api_keys.models import ApiKeyScope


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    scopes: list[ApiKeyScope] = Field(min_length=1, max_length=10)
    expires_at: datetime | None = None

    @field_validator("name", "description")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        return normalized or None

    @field_validator("scopes")
    @classmethod
    def ensure_unique_scopes(cls, value: list[ApiKeyScope]) -> list[ApiKeyScope]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_expiration(self) -> ApiKeyCreateRequest:
        if self.expires_at is not None and _to_utc(self.expires_at) <= datetime.now(UTC):
            msg = "API key expiration must be in the future."
            raise ValueError(msg)
        return self


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    key_prefix: str
    scopes: list[ApiKeyScope]
    expires_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None
    revoked_at: datetime | None
    revoke_reason: str | None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    plaintext_key: str


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
