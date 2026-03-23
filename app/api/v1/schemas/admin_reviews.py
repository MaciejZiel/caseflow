"""Schemas for platform admin review workflow endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.admin_reviews.models import AdminReviewPriority, AdminReviewStatus
from app.domain.organizations.models import OrganizationStatus


def _normalize_title(value: str) -> str:
    normalized = " ".join(value.split()).strip()
    if not normalized:
        msg = "Provide a non-empty title."
        raise ValueError(msg)
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class AdminReviewCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    priority: AdminReviewPriority | None = None
    due_at: datetime | None = None
    assigned_to_user_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return _normalize_title(value)

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class AdminReviewUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    status: AdminReviewStatus | None = None
    priority: AdminReviewPriority | None = None
    due_at: datetime | None = None
    assigned_to_user_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_title(value)

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_payload(self) -> AdminReviewUpdateRequest:
        if not self.model_fields_set:
            msg = "Provide at least one field to update."
            raise ValueError(msg)
        return self


class AdminReviewCommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "Provide a non-empty comment."
            raise ValueError(msg)
        return normalized


class AdminReviewAutoOpenRequest(BaseModel):
    min_risk_score: int = Field(default=50, ge=1, le=1_000)
    limit: int = Field(default=25, ge=1, le=100)
    assigned_to_user_id: UUID | None = None
    due_in_days: int | None = Field(default=None, ge=1, le=90)


class AdminReviewUserResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str


class AdminReviewOrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: OrganizationStatus


class AdminReviewCommentResponse(BaseModel):
    id: UUID
    author: AdminReviewUserResponse
    body: str
    created_at: datetime


class AdminReviewResponse(BaseModel):
    id: UUID
    organization: AdminReviewOrganizationResponse
    title: str
    summary: str | None
    status: AdminReviewStatus
    priority: AdminReviewPriority
    due_at: datetime | None
    resolved_at: datetime | None
    risk_score_snapshot: int
    risk_level_snapshot: str
    anomaly_count_snapshot: int
    top_anomaly_codes_snapshot: list[str]
    created_by: AdminReviewUserResponse
    assigned_to: AdminReviewUserResponse | None
    comment_count: int
    last_comment_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminReviewDetailResponse(AdminReviewResponse):
    comments: list[AdminReviewCommentResponse]


class AdminReviewSummaryResponse(BaseModel):
    total_reviews: int
    counts_by_status: dict[str, int]
    counts_by_priority: dict[str, int]
    active_review_count: int
    overdue_review_count: int
    due_today_count: int
    unassigned_active_review_count: int


class AdminReviewAutoOpenPreviewItemResponse(BaseModel):
    organization: AdminReviewOrganizationResponse
    risk_score: int
    risk_level: str
    anomaly_count: int
    top_anomaly_codes: list[str]
    has_active_review: bool
    active_review_id: UUID | None
    suggested_priority: AdminReviewPriority
    suggested_title: str


class AdminReviewAutoOpenResultItemResponse(BaseModel):
    organization: AdminReviewOrganizationResponse
    outcome: str
    review_id: UUID | None
    reason: str | None
    risk_score: int
    suggested_priority: AdminReviewPriority


class AdminReviewAutoOpenResponse(BaseModel):
    created_count: int
    skipped_count: int
    results: list[AdminReviewAutoOpenResultItemResponse]
