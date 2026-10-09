"""Reporting, search and export services."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.actors import ActorContext
from app.application.services.api_keys import ApiKeyContext, ApiKeyService
from app.core.errors import PermissionDeniedError
from app.domain.cases.models import Case, CaseStatus
from app.domain.organizations.models import OrganizationRole

REPORT_VIEWER_ROLES = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.REVIEWER,
    }
)


class ReportingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def case_summary(self, *, actor: ActorContext) -> dict[str, object]:
        self._ensure_report_access(actor)
        organization_id = actor.organization.id
        now = datetime.now(UTC)
        due_soon = now + timedelta(days=7)

        total_cases = (
            self.session.scalar(
                select(func.count())
                .select_from(Case)
                .where(Case.organization_id == organization_id)
            )
            or 0
        )
        archived_cases = (
            self.session.scalar(
                select(func.count())
                .select_from(Case)
                .where(
                    Case.organization_id == organization_id,
                    Case.status == CaseStatus.ARCHIVED,
                )
            )
            or 0
        )
        overdue_cases = (
            self.session.scalar(
                select(func.count())
                .select_from(Case)
                .where(
                    Case.organization_id == organization_id,
                    Case.archived_at.is_(None),
                    Case.due_date.is_not(None),
                    Case.due_date < now,
                )
            )
            or 0
        )
        due_next_7_days = (
            self.session.scalar(
                select(func.count())
                .select_from(Case)
                .where(
                    Case.organization_id == organization_id,
                    Case.archived_at.is_(None),
                    Case.due_date.is_not(None),
                    Case.due_date >= now,
                    Case.due_date <= due_soon,
                )
            )
            or 0
        )

        status_counts = {
            status.value: count
            for status, count in self.session.execute(
                select(Case.status, func.count())
                .where(Case.organization_id == organization_id)
                .group_by(Case.status)
            )
        }
        priority_counts = {
            priority.value: count
            for priority, count in self.session.execute(
                select(Case.priority, func.count())
                .where(Case.organization_id == organization_id)
                .group_by(Case.priority)
            )
        }
        return {
            "total_cases": total_cases,
            "active_cases": total_cases - archived_cases,
            "archived_cases": archived_cases,
            "overdue_cases": overdue_cases,
            "due_next_7_days": due_next_7_days,
            "status_counts": status_counts,
            "priority_counts": priority_counts,
        }

    def search_cases(
        self,
        *,
        actor: ActorContext,
        query: str,
        limit: int,
    ) -> list[Case]:
        pattern = f"%{query.strip()}%"
        return list(
            self.session.scalars(
                select(Case)
                .where(
                    Case.organization_id == actor.organization.id,
                    or_(
                        Case.title.ilike(pattern),
                        Case.description.ilike(pattern),
                        Case.external_id.ilike(pattern),
                    ),
                )
                .order_by(Case.updated_at.desc(), Case.created_at.desc())
                .limit(limit)
            )
        )

    def export_cases_csv(
        self,
        *,
        api_key: ApiKeyContext,
        limit: int,
        status: CaseStatus | None = None,
        updated_after: datetime | None = None,
        external_id: str | None = None,
    ) -> str:
        cases = ApiKeyService(self.session).list_cases_for_integration(
            api_key=api_key,
            limit=limit,
            status=status,
            external_id=external_id,
            updated_after=updated_after,
        )
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "id",
                "external_id",
                "title",
                "status",
                "priority",
                "owner_user_id",
                "due_date",
                "archived_at",
                "created_at",
                "updated_at",
            ],
        )
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "id": str(case.id),
                    "external_id": case.external_id or "",
                    "title": case.title,
                    "status": case.status.value,
                    "priority": case.priority.value,
                    "owner_user_id": str(case.owner_user_id) if case.owner_user_id else "",
                    "due_date": _serialize_datetime(case.due_date),
                    "archived_at": _serialize_datetime(case.archived_at),
                    "created_at": _serialize_datetime(case.created_at),
                    "updated_at": _serialize_datetime(case.updated_at),
                }
            )
        return buffer.getvalue()

    def _ensure_report_access(self, actor: ActorContext) -> None:
        if actor.membership.role not in REPORT_VIEWER_ROLES:
            raise PermissionDeniedError("You do not have permission to access reports.")


def _serialize_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()
