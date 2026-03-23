"""Schemas for platform admin notifications."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.api.v1.schemas.admin_reviews import (
    AdminReviewOrganizationResponse,
    AdminReviewUserResponse,
)
from app.domain.admin_notifications.models import AdminNotificationType


class AdminNotificationResponse(BaseModel):
    id: UUID
    notification_type: AdminNotificationType
    title: str
    body: str
    organization: AdminReviewOrganizationResponse | None
    review_id: UUID | None
    metadata: dict[str, object]
    read_at: datetime | None
    created_at: datetime


class AdminNotificationSummaryResponse(BaseModel):
    unread_count: int
    counts_by_type: dict[str, int]


class AdminNotificationMarkAllReadResponse(BaseModel):
    updated_count: int


class AdminNotificationPreferenceResponse(BaseModel):
    user: AdminReviewUserResponse
    email_enabled: bool
    notify_on_review_auto_opened: bool
    notify_on_review_overdue_escalated: bool


class AdminNotificationPreferenceUpdateRequest(BaseModel):
    email_enabled: bool | None = None
    notify_on_review_auto_opened: bool | None = None
    notify_on_review_overdue_escalated: bool | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> AdminNotificationPreferenceUpdateRequest:
        if not self.model_fields_set:
            msg = "Provide at least one field to update."
            raise ValueError(msg)
        return self
