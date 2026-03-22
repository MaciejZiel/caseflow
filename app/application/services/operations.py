"""Organization-scoped operational maintenance services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.actors import ActorContext
from app.application.services.documents import DocumentService
from app.application.services.emails import EmailOutboxService
from app.application.services.webhooks import WebhookService
from app.core.errors import PermissionDeniedError
from app.domain.api_keys.models import ApiKey
from app.domain.cases.models import Case, CaseStatus
from app.domain.documents.models import Document
from app.domain.emails.models import OutboundEmail, OutboundEmailStatus
from app.domain.jobs.models import ProcessingJob, ProcessingJobStatus
from app.domain.organizations.models import OrganizationMembership, OrganizationRole
from app.domain.webhooks.models import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint

OPERATIONS_MANAGER_ROLES = frozenset({OrganizationRole.OWNER, OrganizationRole.ADMIN})


@dataclass(slots=True)
class OperationsRetryDueResult:
    processed_document_jobs: int
    processed_webhook_deliveries: int
    processed_emails: int


@dataclass(slots=True)
class OperationsFailureItem:
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


class OperationsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_summary(self, *, actor: ActorContext) -> dict[str, object]:
        self._ensure_manage_permission(actor)
        organization_id = actor.organization.id
        now = datetime.now(UTC)

        active_members = self.session.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active.is_(True),
            )
        ) or 0
        active_webhook_endpoints = self.session.scalar(
            select(func.count())
            .select_from(WebhookEndpoint)
            .where(
                WebhookEndpoint.organization_id == organization_id,
                WebhookEndpoint.is_active.is_(True),
            )
        ) or 0
        active_api_keys = self.session.scalar(
            select(func.count())
            .select_from(ApiKey)
            .where(
                ApiKey.organization_id == organization_id,
                ApiKey.revoked_at.is_(None),
                or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
            )
        ) or 0
        archived_cases = self.session.scalar(
            select(func.count())
            .select_from(Case)
            .where(
                Case.organization_id == organization_id,
                Case.status == CaseStatus.ARCHIVED,
            )
        ) or 0
        total_cases = self.session.scalar(
            select(func.count())
            .select_from(Case)
            .where(Case.organization_id == organization_id)
        ) or 0

        return {
            "organization_id": organization_id,
            "active_members": active_members,
            "active_webhook_endpoints": active_webhook_endpoints,
            "active_api_keys": active_api_keys,
            "open_cases": total_cases - archived_cases,
            "archived_cases": archived_cases,
            "documents_by_status": self._group_counts(
                model=Document,
                organization_id=organization_id,
                group_column=Document.status,
            ),
            "jobs_by_status": self._group_counts(
                model=ProcessingJob,
                organization_id=organization_id,
                group_column=ProcessingJob.status,
            ),
            "webhook_deliveries_by_status": self._group_counts(
                model=WebhookDelivery,
                organization_id=organization_id,
                group_column=WebhookDelivery.status,
            ),
            "emails_by_status": self._group_counts(
                model=OutboundEmail,
                organization_id=organization_id,
                group_column=OutboundEmail.status,
            ),
        }

    def list_recent_failures(
        self,
        *,
        actor: ActorContext,
        limit: int,
    ) -> list[OperationsFailureItem]:
        self._ensure_manage_permission(actor)
        organization_id = actor.organization.id

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

    def retry_due_items(
        self,
        *,
        actor: ActorContext,
        limit_per_queue: int,
    ) -> OperationsRetryDueResult:
        self._ensure_manage_permission(actor)
        organization_id = actor.organization.id
        processed_document_jobs = len(
            DocumentService(self.session).process_due_jobs(
                limit=limit_per_queue,
                organization_id=organization_id,
            )
        )
        processed_webhook_deliveries = len(
            WebhookService(self.session).process_due_deliveries(
                limit=limit_per_queue,
                organization_id=organization_id,
            )
        )
        processed_emails = len(
            EmailOutboxService(self.session).process_due_emails(
                limit=limit_per_queue,
                organization_id=organization_id,
            )
        )
        return OperationsRetryDueResult(
            processed_document_jobs=processed_document_jobs,
            processed_webhook_deliveries=processed_webhook_deliveries,
            processed_emails=processed_emails,
        )

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

    @staticmethod
    def _ensure_manage_permission(actor: ActorContext) -> None:
        if actor.membership.role not in OPERATIONS_MANAGER_ROLES:
            raise PermissionDeniedError("Only owners and admins can access operations.")
