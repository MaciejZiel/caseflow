"""Schemas for webhook endpoint management and delivery inspection."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.webhooks.models import WebhookDeliveryStatus


def _validate_target_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        msg = "Provide a valid http or https webhook target URL."
        raise ValueError(msg)
    return value


class WebhookEndpointCreateRequest(BaseModel):
    target_url: str = Field(min_length=10, max_length=500)
    signing_secret: str | None = Field(default=None, min_length=16, max_length=255)
    is_active: bool = True

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: str) -> str:
        return _validate_target_url(value)


class WebhookEndpointUpdateRequest(BaseModel):
    target_url: str | None = Field(default=None, min_length=10, max_length=500)
    signing_secret: str | None = Field(default=None, min_length=16, max_length=255)
    is_active: bool | None = None

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_target_url(value)

    @model_validator(mode="after")
    def validate_payload(self) -> WebhookEndpointUpdateRequest:
        if self.target_url is None and self.signing_secret is None and self.is_active is None:
            msg = "Provide at least one field to update."
            raise ValueError(msg)
        return self


class WebhookEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_url: str
    is_active: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    endpoint_id: UUID
    event_type: str
    status: WebhookDeliveryStatus
    http_status: int | None
    attempts: int
    request_body_json: dict[str, object]
    response_body_excerpt: str | None
    next_retry_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
