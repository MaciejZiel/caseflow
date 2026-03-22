"""Schemas for platform admin endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.api.v1.schemas.auth import OrganizationResponse
from app.api.v1.schemas.operations import OperationsFailureResponse
from app.domain.organizations.models import OrganizationStatus


class AdminAuditEventResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    event_type: str
    entity_type: str
    entity_id: UUID
    created_at: datetime


class AdminOrganizationListItemResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime
    total_members: int
    active_members: int
    active_auth_sessions: int
    open_cases: int
    archived_cases: int
    failed_jobs: int
    failed_webhook_deliveries: int
    failed_emails: int
    last_activity_at: datetime | None


class AdminOrganizationDetailResponse(BaseModel):
    organization: OrganizationResponse
    total_members: int
    active_members: int
    members_by_role: dict[str, int]
    active_api_keys: int
    active_webhook_endpoints: int
    active_auth_sessions: int
    total_cases: int
    open_cases: int
    archived_cases: int
    total_documents: int
    documents_by_status: dict[str, int]
    jobs_by_status: dict[str, int]
    webhook_deliveries_by_status: dict[str, int]
    emails_by_status: dict[str, int]
    recent_failures: list[OperationsFailureResponse]
    recent_audit_events: list[AdminAuditEventResponse]
    last_activity_at: datetime | None


class AdminOrganizationStatusChangeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        return normalized or None


class AdminOrganizationStatusChangeResponse(BaseModel):
    organization: OrganizationResponse
    previous_status: OrganizationStatus
    current_status: OrganizationStatus
    revoked_auth_sessions: int
    reason: str | None
