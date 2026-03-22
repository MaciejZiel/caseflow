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
    subscribed_event_types: list[str] = Field(default_factory=list, max_length=50)
    is_active: bool = True

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: str) -> str:
        return _validate_target_url(value)

    @field_validator("subscribed_event_types")
    @classmethod
    def normalize_subscribed_event_types(cls, value: list[str]) -> list[str]:
        return _normalize_event_types(value)


class WebhookEndpointUpdateRequest(BaseModel):
    target_url: str | None = Field(default=None, min_length=10, max_length=500)
    signing_secret: str | None = Field(default=None, min_length=16, max_length=255)
    subscribed_event_types: list[str] | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_target_url(value)

    @field_validator("subscribed_event_types")
    @classmethod
    def validate_subscribed_event_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalize_event_types(value)

    @model_validator(mode="after")
    def validate_payload(self) -> WebhookEndpointUpdateRequest:
        if (
            self.target_url is None
            and self.signing_secret is None
            and self.subscribed_event_types is None
            and self.is_active is None
        ):
            msg = "Provide at least one field to update."
            raise ValueError(msg)
        return self


class WebhookEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_url: str
    subscribed_event_types: list[str]
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
    replayed_from_delivery_id: UUID | None
    next_retry_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


def _normalize_event_types(value: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in value:
        candidate = item.strip().lower()
        if not candidate:
            continue
        if len(candidate) > 120:
            msg = "Webhook event types must be 120 characters or fewer."
            raise ValueError(msg)
        normalized.append(candidate)
    return list(dict.fromkeys(normalized))
