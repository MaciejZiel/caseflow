"""Platform admin services for cross-tenant organization management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.actors import ActorContext
from app.application.services.events import EventPublisher
from app.application.services.operations import OperationsFailureItem
from app.core.errors import DomainValidationError, NotFoundError, PermissionDeniedError
from app.domain.api_keys.models import ApiKey
from app.domain.audit.models import AuditLog
from app.domain.auth.models import AuthSession
from app.domain.cases.models import Case, CaseStatus
from app.domain.documents.models import Document
from app.domain.emails.models import OutboundEmail, OutboundEmailStatus
from app.domain.jobs.models import ProcessingJob, ProcessingJobStatus
from app.domain.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from app.domain.users.models import User
from app.domain.webhooks.models import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint


@dataclass(slots=True)
class AdminOrganizationListItem:
    organization: Organization
    total_members: int
    active_members: int
    active_auth_sessions: int
    open_cases: int
    archived_cases: int
    failed_jobs: int
    failed_webhook_deliveries: int
    failed_emails: int
    last_activity_at: datetime | None


@dataclass(slots=True)
class AdminOrganizationDetail:
    organization: Organization
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
    recent_failures: list[OperationsFailureItem]
    recent_audit_events: list[AuditLog]
    last_activity_at: datetime | None


@dataclass(slots=True)
class AdminOrganizationStatusChangeResult:
    organization: Organization
    previous_status: OrganizationStatus
    current_status: OrganizationStatus
    revoked_auth_sessions: int
    reason: str | None


class AdminService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_organizations(
        self,
        *,
        actor: ActorContext,
        status: OrganizationStatus | None,
        search: str | None,
        limit: int,
    ) -> list[AdminOrganizationListItem]:
        self._ensure_superuser(actor)
        normalized_search = " ".join(search.split()).strip().lower() if search else None
        now = datetime.now(UTC)

        total_members = (
            select(func.count(OrganizationMembership.id))
            .where(OrganizationMembership.organization_id == Organization.id)
            .correlate(Organization)
            .scalar_subquery()
        )
        active_members = (
            select(func.count(OrganizationMembership.id))
            .where(
                OrganizationMembership.organization_id == Organization.id,
                OrganizationMembership.is_active.is_(True),
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        active_auth_sessions = (
            select(func.count(AuthSession.id))
            .select_from(AuthSession)
            .join(AuthSession.user)
            .join(AuthSession.membership)
            .where(
                AuthSession.organization_id == Organization.id,
                AuthSession.revoked_at.is_(None),
                AuthSession.refresh_token_expires_at > now,
                User.is_active.is_(True),
                OrganizationMembership.is_active.is_(True),
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        archived_cases = (
            select(func.count(Case.id))
            .where(
                Case.organization_id == Organization.id,
                Case.status == CaseStatus.ARCHIVED,
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        open_cases = (
            select(func.count(Case.id))
            .where(
                Case.organization_id == Organization.id,
                Case.status != CaseStatus.ARCHIVED,
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        failed_jobs = (
            select(func.count(ProcessingJob.id))
            .where(
                ProcessingJob.organization_id == Organization.id,
                ProcessingJob.status.in_(
                    [ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTERED]
                ),
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        failed_webhook_deliveries = (
            select(func.count(WebhookDelivery.id))
            .where(
                WebhookDelivery.organization_id == Organization.id,
                WebhookDelivery.status == WebhookDeliveryStatus.FAILED,
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        failed_emails = (
            select(func.count(OutboundEmail.id))
            .where(
                OutboundEmail.organization_id == Organization.id,
                OutboundEmail.status == OutboundEmailStatus.FAILED,
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        last_activity_at = (
            select(func.max(AuditLog.created_at))
            .where(AuditLog.organization_id == Organization.id)
            .correlate(Organization)
            .scalar_subquery()
        )

        query = (
            select(
                Organization,
                total_members.label("total_members"),
                active_members.label("active_members"),
                active_auth_sessions.label("active_auth_sessions"),
                open_cases.label("open_cases"),
                archived_cases.label("archived_cases"),
                failed_jobs.label("failed_jobs"),
                failed_webhook_deliveries.label("failed_webhook_deliveries"),
                failed_emails.label("failed_emails"),
                last_activity_at.label("last_activity_at"),
            )
            .order_by(Organization.created_at.desc())
            .limit(limit)
        )

        if status is not None:
            query = query.where(Organization.status == status)
        if normalized_search is not None:
            search_pattern = f"%{normalized_search}%"
            query = query.where(
                or_(
                    func.lower(Organization.name).like(search_pattern),
                    func.lower(Organization.slug).like(search_pattern),
                )
            )

        return [
            AdminOrganizationListItem(
                organization=row.Organization,
                total_members=row.total_members or 0,
                active_members=row.active_members or 0,
                active_auth_sessions=row.active_auth_sessions or 0,
                open_cases=row.open_cases or 0,
                archived_cases=row.archived_cases or 0,
                failed_jobs=row.failed_jobs or 0,
                failed_webhook_deliveries=row.failed_webhook_deliveries or 0,
                failed_emails=row.failed_emails or 0,
                last_activity_at=row.last_activity_at,
            )
            for row in self.session.execute(query)
        ]

    def get_organization_detail(
        self,
        *,
        actor: ActorContext,
        organization_id: UUID,
        failure_limit: int = 10,
        audit_limit: int = 10,
    ) -> AdminOrganizationDetail:
        self._ensure_superuser(actor)
        organization = self._get_organization(organization_id)
        now = datetime.now(UTC)

        total_members = self._count_rows(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == organization_id
            )
        )
        active_members = self._count_rows(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        active_api_keys = self._count_rows(
            select(func.count(ApiKey.id)).where(
                ApiKey.organization_id == organization_id,
                ApiKey.revoked_at.is_(None),
                or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
            )
        )
        active_webhook_endpoints = self._count_rows(
            select(func.count(WebhookEndpoint.id)).where(
                WebhookEndpoint.organization_id == organization_id,
                WebhookEndpoint.is_active.is_(True),
            )
        )
        active_auth_sessions = self._count_rows(
            select(func.count(AuthSession.id))
            .select_from(AuthSession)
            .join(AuthSession.user)
            .join(AuthSession.membership)
            .where(
                AuthSession.organization_id == organization_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.refresh_token_expires_at > now,
                User.is_active.is_(True),
                OrganizationMembership.is_active.is_(True),
            )
        )
        total_cases = self._count_rows(
            select(func.count(Case.id)).where(Case.organization_id == organization_id)
        )
        archived_cases = self._count_rows(
            select(func.count(Case.id)).where(
                Case.organization_id == organization_id,
                Case.status == CaseStatus.ARCHIVED,
            )
        )
        total_documents = self._count_rows(
            select(func.count(Document.id)).where(Document.organization_id == organization_id)
        )
        recent_audit_events = list(
            self.session.scalars(
                select(AuditLog)
                .where(AuditLog.organization_id == organization_id)
                .order_by(AuditLog.created_at.desc())
                .limit(audit_limit)
            )
        )

        return AdminOrganizationDetail(
            organization=organization,
            total_members=total_members,
            active_members=active_members,
            members_by_role=self._members_by_role(organization_id),
            active_api_keys=active_api_keys,
            active_webhook_endpoints=active_webhook_endpoints,
            active_auth_sessions=active_auth_sessions,
            total_cases=total_cases,
            open_cases=total_cases - archived_cases,
            archived_cases=archived_cases,
            total_documents=total_documents,
            documents_by_status=self._group_counts(
                model=Document,
                organization_id=organization_id,
                group_column=Document.status,
            ),
            jobs_by_status=self._group_counts(
                model=ProcessingJob,
                organization_id=organization_id,
                group_column=ProcessingJob.status,
            ),
            webhook_deliveries_by_status=self._group_counts(
                model=WebhookDelivery,
                organization_id=organization_id,
                group_column=WebhookDelivery.status,
            ),
            emails_by_status=self._group_counts(
                model=OutboundEmail,
                organization_id=organization_id,
                group_column=OutboundEmail.status,
            ),
            recent_failures=self._recent_failures(
                organization_id=organization_id,
                limit=failure_limit,
            ),
            recent_audit_events=recent_audit_events,
            last_activity_at=recent_audit_events[0].created_at if recent_audit_events else None,
        )

    def suspend_organization(
        self,
        *,
        actor: ActorContext,
        organization_id: UUID,
        reason: str | None,
    ) -> AdminOrganizationStatusChangeResult:
        self._ensure_superuser(actor)
        organization = self._get_organization(organization_id)
        if organization.id == actor.organization.id:
            raise DomainValidationError(
                "current_admin_organization_suspend_forbidden",
                "Platform admins cannot suspend the organization tied to the current session.",
            )
        if organization.status == OrganizationStatus.ARCHIVED:
            raise DomainValidationError(
                "archived_organization_suspend_forbidden",
                "Archived organizations cannot be suspended.",
            )

        previous_status = organization.status
        revoked_auth_sessions = 0
        if organization.status != OrganizationStatus.SUSPENDED:
            organization.status = OrganizationStatus.SUSPENDED
            revoked_auth_sessions = self._revoke_organization_auth_sessions(
                organization_id=organization.id,
                reason="organization_suspended",
            )
            EventPublisher(self.session).record_event(
                organization_id=organization.id,
                actor_user_id=actor.user.id,
                event_type="organization.suspended",
                entity_type="organization",
                entity_id=organization.id,
                old_values={"status": previous_status},
                new_values={"status": organization.status},
                metadata={
                    "reason": reason,
                    "scope": "platform_admin",
                    "revoked_auth_sessions": revoked_auth_sessions,
                },
                deliver_webhooks=False,
            )
            self.session.commit()
            self.session.refresh(organization)

        return AdminOrganizationStatusChangeResult(
            organization=organization,
            previous_status=previous_status,
            current_status=organization.status,
            revoked_auth_sessions=revoked_auth_sessions,
            reason=reason,
        )

    def reactivate_organization(
        self,
        *,
        actor: ActorContext,
        organization_id: UUID,
        reason: str | None,
    ) -> AdminOrganizationStatusChangeResult:
        self._ensure_superuser(actor)
        organization = self._get_organization(organization_id)
        if organization.status == OrganizationStatus.ARCHIVED:
            raise DomainValidationError(
                "archived_organization_reactivation_forbidden",
                "Archived organizations cannot be reactivated.",
            )

        previous_status = organization.status
        if organization.status != OrganizationStatus.ACTIVE:
            organization.status = OrganizationStatus.ACTIVE
            EventPublisher(self.session).record_event(
                organization_id=organization.id,
                actor_user_id=actor.user.id,
                event_type="organization.reactivated",
                entity_type="organization",
                entity_id=organization.id,
                old_values={"status": previous_status},
                new_values={"status": organization.status},
                metadata={
                    "reason": reason,
                    "scope": "platform_admin",
                },
                deliver_webhooks=False,
            )
            self.session.commit()
            self.session.refresh(organization)

        return AdminOrganizationStatusChangeResult(
            organization=organization,
            previous_status=previous_status,
            current_status=organization.status,
            revoked_auth_sessions=0,
            reason=reason,
        )

    @staticmethod
    def _ensure_superuser(actor: ActorContext) -> None:
        if not actor.user.is_superuser:
            raise PermissionDeniedError("Only platform admins can access admin endpoints.")

    def _get_organization(self, organization_id: UUID) -> Organization:
        organization = self.session.get(Organization, organization_id)
        if organization is None:
            raise NotFoundError("organization", "Organization does not exist.")
        return organization

    def _count_rows(self, statement) -> int:
        return int(self.session.scalar(statement) or 0)

    def _group_counts(self, *, model, organization_id: UUID, group_column) -> dict[str, int]:
        return {
            getattr(group_value, "value", str(group_value)): count
            for group_value, count in self.session.execute(
                select(group_column, func.count())
                .select_from(model)
                .where(model.organization_id == organization_id)
                .group_by(group_column)
            )
        }

    def _members_by_role(self, organization_id: UUID) -> dict[str, int]:
        return {
            role.value: count
            for role, count in self.session.execute(
                select(OrganizationMembership.role, func.count())
                .where(OrganizationMembership.organization_id == organization_id)
                .group_by(OrganizationMembership.role)
            )
        }

    def _recent_failures(
        self,
        *,
        organization_id: UUID,
        limit: int,
    ) -> list[OperationsFailureItem]:
        job_failures = [
            OperationsFailureItem(
                source="processing_job",
                id=job.id,
                status=job.status.value,
                summary=job.job_type.value,
                reference_id=job.document_id,
                reference_label="document_id",
                attempts=job.attempts,
                last_error=job.last_error,
                next_retry_at=job.next_retry_at,
                created_at=job.created_at,
            )
            for job in self.session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.organization_id == organization_id,
                    ProcessingJob.status.in_(
                        [ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTERED]
                    ),
                )
                .order_by(ProcessingJob.created_at.desc())
                .limit(limit)
            )
        ]
        webhook_failures = [
            OperationsFailureItem(
                source="webhook_delivery",
                id=delivery.id,
                status=delivery.status.value,
                summary=delivery.event_type,
                reference_id=delivery.endpoint_id,
                reference_label="endpoint_id",
                attempts=delivery.attempts,
                last_error=delivery.response_body_excerpt,
                next_retry_at=delivery.next_retry_at,
                created_at=delivery.created_at,
            )
            for delivery in self.session.scalars(
                select(WebhookDelivery)
                .where(
                    WebhookDelivery.organization_id == organization_id,
                    WebhookDelivery.status == WebhookDeliveryStatus.FAILED,
                )
                .order_by(WebhookDelivery.created_at.desc())
                .limit(limit)
            )
        ]
        email_failures = [
            OperationsFailureItem(
                source="outbound_email",
                id=email.id,
                status=email.status.value,
                summary=email.template_key,
                reference_id=None,
                reference_label=email.recipient_email,
                attempts=email.attempts,
                last_error=email.last_error,
                next_retry_at=email.next_retry_at,
                created_at=email.created_at,
            )
            for email in self.session.scalars(
                select(OutboundEmail)
                .where(
                    OutboundEmail.organization_id == organization_id,
                    OutboundEmail.status == OutboundEmailStatus.FAILED,
                )
                .order_by(OutboundEmail.created_at.desc())
                .limit(limit)
            )
        ]

        failures = sorted(
            [*job_failures, *webhook_failures, *email_failures],
            key=lambda item: item.created_at,
            reverse=True,
        )
        return failures[:limit]

    def _revoke_organization_auth_sessions(self, *, organization_id: UUID, reason: str) -> int:
        now = datetime.now(UTC)
        active_sessions = list(
            self.session.scalars(
                select(AuthSession).where(
                    AuthSession.organization_id == organization_id,
                    AuthSession.revoked_at.is_(None),
                )
            )
        )
        for auth_session in active_sessions:
            auth_session.revoked_at = now
            auth_session.revoke_reason = reason
        return len(active_sessions)
