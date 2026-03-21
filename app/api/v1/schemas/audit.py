"""Schemas for audit log inspection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID | None
    event_type: str
    entity_type: str
    entity_id: UUID
    old_values_json: dict[str, object] | None
    new_values_json: dict[str, object] | None
    metadata_json: dict[str, object] | None
    created_at: datetime
