"""Audit log query services."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.audit.models import AuditLog


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_entity_logs(
        self,
        *,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> list[AuditLog]:
        return list(
            self.session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.entity_type == entity_type,
                    AuditLog.entity_id == entity_id,
                )
                .order_by(AuditLog.created_at.asc())
            )
        )
