"""Schemas for organization operations endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OperationsSummaryResponse(BaseModel):
    organization_id: UUID
    active_members: int
    active_webhook_endpoints: int
    active_api_keys: int
    open_cases: int
    archived_cases: int
    documents_by_status: dict[str, int]
    jobs_by_status: dict[str, int]
    webhook_deliveries_by_status: dict[str, int]
    emails_by_status: dict[str, int]


class OperationsFailureResponse(BaseModel):
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


class OperationsRetryDueResponse(BaseModel):
    processed_document_jobs: int
    processed_webhook_deliveries: int
    processed_emails: int
