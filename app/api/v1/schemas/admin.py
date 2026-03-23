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


class AdminBulkOrganizationStatusChangeRequest(BaseModel):
    organization_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: str
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("organization_ids")
    @classmethod
    def ensure_unique_organization_ids(cls, value: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(value))

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in {"suspend", "reactivate"}:
            msg = "Action must be suspend or reactivate."
            raise ValueError(msg)
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        return normalized or None


class AdminBulkOrganizationStatusChangeItemResponse(BaseModel):
    organization_id: UUID
    organization_slug: str | None
    outcome: str
    previous_status: OrganizationStatus | None
    current_status: OrganizationStatus | None
    revoked_auth_sessions: int
    error_code: str | None
    error_message: str | None


class AdminBulkOrganizationStatusChangeResponse(BaseModel):
    action: str
    total_requested: int
    updated_count: int
    failed_count: int
    results: list[AdminBulkOrganizationStatusChangeItemResponse]


class AdminOverviewResponse(BaseModel):
    total_organizations: int
    organizations_by_status: dict[str, int]
    active_auth_sessions: int
    active_api_keys: int
    open_cases: int
    failed_jobs: int
    failed_webhook_deliveries: int
    failed_emails: int


class AdminFailureResponse(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_slug: str
    source: str
    id: UUID
    status: str
    summary: str
    reference_id: UUID | None
    reference_label: str | None
    attempts: int
    last_error: str | None
    next_retry_at: datetime | None
    created_at: datetime


class AdminRetryDueResponse(BaseModel):
    processed_document_jobs: int
    processed_webhook_deliveries: int
    processed_admin_notification_digests: int
    processed_emails: int


class AdminAnomalyResponse(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_slug: str
    severity: str
    code: str
    summary: str
    detected_at: datetime
    metadata: dict[str, object]


class AdminRiskReportItemResponse(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_slug: str
    status: OrganizationStatus
    risk_score: int
    risk_level: str
    anomaly_count: int
    critical_anomaly_count: int
    warning_anomaly_count: int
    info_anomaly_count: int
    top_anomaly_codes: list[str]
    active_members: int
    active_auth_sessions: int
    open_cases: int
    archived_cases: int
    failed_jobs: int
    failed_webhook_deliveries: int
    failed_emails: int
    last_activity_at: datetime | None
