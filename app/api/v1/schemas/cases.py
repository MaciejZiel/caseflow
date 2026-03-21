"""Schemas for case CRUD endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.cases.models import CasePriority, CaseStatus


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    external_id: str | None = Field(default=None, max_length=120)
    priority: CasePriority = CasePriority.NORMAL
    owner_user_id: UUID | None = None
    due_date: datetime | None = None


class CaseUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=10_000)
    external_id: str | None = Field(default=None, max_length=120)
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    owner_user_id: UUID | None = None
    due_date: datetime | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> CaseUpdateRequest:
        if all(
            value is None
            for value in (
                self.title,
                self.description,
                self.external_id,
                self.status,
                self.priority,
                self.owner_user_id,
                self.due_date,
            )
        ):
            msg = "Provide at least one field to update."
            raise ValueError(msg)
        if self.status == CaseStatus.ARCHIVED:
            msg = "Use the archive endpoint to archive a case."
            raise ValueError(msg)
        return self


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str | None
    title: str
    description: str | None
    status: CaseStatus
    priority: CasePriority
    owner_user_id: UUID | None
    created_by: UUID
    due_date: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
