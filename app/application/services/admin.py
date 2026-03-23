"""Platform admin services for cross-tenant organization management."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.application.actors import ActorContext
from app.application.services.documents import DocumentService
from app.application.services.emails import EmailOutboxService
from app.application.services.events import EventPublisher
from app.application.services.operations import OperationsFailureItem
from app.application.services.webhooks import WebhookService
from app.core.config import get_settings
from app.core.errors import (
    CaseFlowError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
)
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
    OrganizationRole,
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


@dataclass(slots=True)
class AdminOverview:
    total_organizations: int
    organizations_by_status: dict[str, int]
    active_auth_sessions: int
    active_api_keys: int
    open_cases: int
    failed_jobs: int
    failed_webhook_deliveries: int
    failed_emails: int


@dataclass(slots=True)
class AdminFailureItem:
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


@dataclass(slots=True)
class AdminRetryDueResult:
    processed_document_jobs: int
    processed_webhook_deliveries: int
    processed_admin_notification_digests: int
    processed_emails: int


@dataclass(slots=True)
class AdminAnomalyItem:
    organization_id: UUID
    organization_name: str
    organization_slug: str
    severity: str
    code: str
    summary: str
    detected_at: datetime
    metadata: dict[str, object]


@dataclass(slots=True)
class AdminBulkOrganizationStatusChangeItem:
    organization_id: UUID
    organization_slug: str | None
    outcome: str
    previous_status: OrganizationStatus | None
    current_status: OrganizationStatus | None
    revoked_auth_sessions: int
    error_code: str | None
    error_message: str | None


@dataclass(slots=True)
class AdminBulkOrganizationStatusChangeResult:
    action: str
    total_requested: int
    updated_count: int
    failed_count: int
    results: list[AdminBulkOrganizationStatusChangeItem]


@dataclass(slots=True)
class AdminRiskReportItem:
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


class AdminService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def list_organizations(
        self,
        *,
        actor: ActorContext,
        status: OrganizationStatus | None,
        search: str | None,
        limit: int,
    ) -> list[AdminOrganizationListItem]:
        self._ensure_superuser(actor)
        return self._fetch_organization_snapshots(
            status=status,
            search=search,
            limit=limit,
            organization_id=None,
        )

    def _fetch_organization_snapshots(
        self,
        *,
        status: OrganizationStatus | None,
        search: str | None,
        limit: int | None,
        organization_id: UUID | None,
    ) -> list[AdminOrganizationListItem]:
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
        )
        if limit is not None:
            query = query.limit(limit)

        if status is not None:
            query = query.where(Organization.status == status)
        if organization_id is not None:
            query = query.where(Organization.id == organization_id)
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

    def get_overview(self, *, actor: ActorContext) -> AdminOverview:
        self._ensure_superuser(actor)
        now = datetime.now(UTC)
        organizations_by_status = {
            status.value: count
            for status, count in self.session.execute(
                select(Organization.status, func.count())
                .select_from(Organization)
                .group_by(Organization.status)
            )
        }
        return AdminOverview(
            total_organizations=self._count_rows(select(func.count(Organization.id))),
            organizations_by_status=organizations_by_status,
            active_auth_sessions=self._count_rows(
                select(func.count(AuthSession.id))
                .select_from(AuthSession)
                .join(AuthSession.user)
                .join(AuthSession.membership)
                .where(
                    AuthSession.revoked_at.is_(None),
                    AuthSession.refresh_token_expires_at > now,
                    User.is_active.is_(True),
                    OrganizationMembership.is_active.is_(True),
                )
            ),
            active_api_keys=self._count_rows(
                select(func.count(ApiKey.id)).where(
                    ApiKey.revoked_at.is_(None),
                    or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
                )
            ),
            open_cases=self._count_rows(
                select(func.count(Case.id)).where(Case.status != CaseStatus.ARCHIVED)
            ),
            failed_jobs=self._count_rows(
                select(func.count(ProcessingJob.id)).where(
                    ProcessingJob.status.in_(
                        [ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTERED]
                    )
                )
            ),
            failed_webhook_deliveries=self._count_rows(
                select(func.count(WebhookDelivery.id)).where(
                    WebhookDelivery.status == WebhookDeliveryStatus.FAILED
                )
            ),
            failed_emails=self._count_rows(
                select(func.count(OutboundEmail.id)).where(
                    OutboundEmail.status == OutboundEmailStatus.FAILED
                )
            ),
        )

    def list_recent_failures(
        self,
        *,
        actor: ActorContext,
        limit: int,
        source: str | None,
    ) -> list[AdminFailureItem]:
        self._ensure_superuser(actor)

        failures: list[AdminFailureItem] = []
        if source in (None, "processing_job"):
            failures.extend(
                AdminFailureItem(
                    organization_id=job.organization_id,
                    organization_name=organization_name,
                    organization_slug=organization_slug,
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
                for job, organization_name, organization_slug in self.session.execute(
                    select(ProcessingJob, Organization.name, Organization.slug)
                    .join(Organization, ProcessingJob.organization_id == Organization.id)
                    .where(
                        ProcessingJob.status.in_(
                            [ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTERED]
                        )
                    )
                    .order_by(ProcessingJob.created_at.desc())
                    .limit(limit)
                )
            )
        if source in (None, "webhook_delivery"):
            failures.extend(
                AdminFailureItem(
                    organization_id=delivery.organization_id,
                    organization_name=organization_name,
                    organization_slug=organization_slug,
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
                for delivery, organization_name, organization_slug in self.session.execute(
                    select(WebhookDelivery, Organization.name, Organization.slug)
                    .join(Organization, WebhookDelivery.organization_id == Organization.id)
                    .where(WebhookDelivery.status == WebhookDeliveryStatus.FAILED)
                    .order_by(WebhookDelivery.created_at.desc())
                    .limit(limit)
                )
            )
        if source in (None, "outbound_email"):
            failures.extend(
                AdminFailureItem(
                    organization_id=email.organization_id,
                    organization_name=organization_name,
                    organization_slug=organization_slug,
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
                for email, organization_name, organization_slug in self.session.execute(
                    select(OutboundEmail, Organization.name, Organization.slug)
                    .join(Organization, OutboundEmail.organization_id == Organization.id)
                    .where(OutboundEmail.status == OutboundEmailStatus.FAILED)
                    .order_by(OutboundEmail.created_at.desc())
                    .limit(limit)
                )
            )

        failures.sort(key=lambda item: item.created_at, reverse=True)
        return failures[:limit]

    def retry_due_items(
        self,
        *,
        actor: ActorContext,
        limit_per_queue: int,
    ) -> AdminRetryDueResult:
        self._ensure_superuser(actor)
        processed_document_jobs = len(
            DocumentService(self.session).process_due_jobs(limit=limit_per_queue)
        )
        processed_webhook_deliveries = len(
            WebhookService(self.session).process_due_deliveries(limit=limit_per_queue)
        )
        from app.application.services.admin_notifications import AdminNotificationService

        processed_admin_notification_digests = AdminNotificationService(
            self.session
        ).process_due_digests(limit=limit_per_queue)
        processed_emails = len(
            EmailOutboxService(self.session).process_due_emails(limit=limit_per_queue)
        )
        return AdminRetryDueResult(
            processed_document_jobs=processed_document_jobs,
            processed_webhook_deliveries=processed_webhook_deliveries,
            processed_admin_notification_digests=processed_admin_notification_digests,
            processed_emails=processed_emails,
        )

    def list_anomalies(
        self,
        *,
        actor: ActorContext,
        severity: str | None,
        limit: int,
    ) -> list[AdminAnomalyItem]:
        self._ensure_superuser(actor)
        anomalies = self._collect_anomalies()
        if severity is not None:
            anomalies = [item for item in anomalies if item.severity == severity]
        anomalies.sort(
            key=lambda item: (
                self._severity_rank(item.severity),
                -item.detected_at.timestamp(),
                item.organization_slug,
                item.code,
            )
        )
        return anomalies[:limit]

    def list_risk_report(
        self,
        *,
        actor: ActorContext,
        status: OrganizationStatus | None,
        search: str | None,
        min_risk_score: int,
        limit: int,
    ) -> list[AdminRiskReportItem]:
        self._ensure_superuser(actor)
        organizations = self._fetch_organization_snapshots(
            status=status,
            search=search,
            limit=None,
            organization_id=None,
        )
        anomaly_index = self._index_anomalies_by_organization(self._collect_anomalies())

        report = [
            self._build_risk_report_item(
                organization=item,
                anomalies=anomaly_index.get(item.organization.id, []),
            )
            for item in organizations
        ]
        report = [item for item in report if item.risk_score >= min_risk_score]
        report.sort(
            key=lambda item: (
                -item.risk_score,
                self._risk_level_rank(item.risk_level),
                -(item.last_activity_at.timestamp() if item.last_activity_at else 0),
                item.organization_slug,
            )
        )
        return report[:limit]

    def get_organization_risk_report(
        self,
        *,
        actor: ActorContext,
        organization_id: UUID,
    ) -> AdminRiskReportItem:
        self._ensure_superuser(actor)
        self._get_organization(organization_id)
        organizations = self._fetch_organization_snapshots(
            status=None,
            search=None,
            limit=1,
            organization_id=organization_id,
        )
        anomaly_index = self._index_anomalies_by_organization(self._collect_anomalies())
        return self._build_risk_report_item(
            organization=organizations[0],
            anomalies=anomaly_index.get(organization_id, []),
        )

    def export_organizations_csv(
        self,
        *,
        actor: ActorContext,
        status: OrganizationStatus | None,
        search: str | None,
        min_risk_score: int,
        limit: int,
    ) -> str:
        report = self.list_risk_report(
            actor=actor,
            status=status,
            search=search,
            min_risk_score=min_risk_score,
            limit=limit,
        )
        buffer = StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "organization_id",
                "organization_name",
                "organization_slug",
                "status",
                "risk_score",
                "risk_level",
                "anomaly_count",
                "critical_anomaly_count",
                "warning_anomaly_count",
                "info_anomaly_count",
                "top_anomaly_codes",
                "active_members",
                "active_auth_sessions",
                "open_cases",
                "archived_cases",
                "failed_jobs",
                "failed_webhook_deliveries",
                "failed_emails",
                "last_activity_at",
            ],
        )
        writer.writeheader()
        for item in report:
            writer.writerow(
                {
                    "organization_id": str(item.organization_id),
                    "organization_name": item.organization_name,
                    "organization_slug": item.organization_slug,
                    "status": item.status.value,
                    "risk_score": item.risk_score,
                    "risk_level": item.risk_level,
                    "anomaly_count": item.anomaly_count,
                    "critical_anomaly_count": item.critical_anomaly_count,
                    "warning_anomaly_count": item.warning_anomaly_count,
                    "info_anomaly_count": item.info_anomaly_count,
                    "top_anomaly_codes": ",".join(item.top_anomaly_codes),
                    "active_members": item.active_members,
                    "active_auth_sessions": item.active_auth_sessions,
                    "open_cases": item.open_cases,
                    "archived_cases": item.archived_cases,
                    "failed_jobs": item.failed_jobs,
                    "failed_webhook_deliveries": item.failed_webhook_deliveries,
                    "failed_emails": item.failed_emails,
                    "last_activity_at": _serialize_datetime(item.last_activity_at),
                }
            )
        return buffer.getvalue()

    def list_organization_activity(
        self,
        *,
        actor: ActorContext,
        organization_id: UUID,
        limit: int,
        event_type: str | None,
        entity_type: str | None,
        actor_user_id: UUID | None,
        since: datetime | None,
    ) -> list[AuditLog]:
        self._ensure_superuser(actor)
        self._get_organization(organization_id)
        query = select(AuditLog).where(AuditLog.organization_id == organization_id)
        if event_type is not None:
            query = query.where(AuditLog.event_type == event_type)
        if entity_type is not None:
            query = query.where(AuditLog.entity_type == entity_type)
        if actor_user_id is not None:
            query = query.where(AuditLog.actor_user_id == actor_user_id)
        if since is not None:
            query = query.where(AuditLog.created_at >= since)
        return list(
            self.session.scalars(query.order_by(AuditLog.created_at.desc()).limit(limit))
        )

    def bulk_change_organization_status(
        self,
        *,
        actor: ActorContext,
        organization_ids: list[UUID],
        action: str,
        reason: str | None,
    ) -> AdminBulkOrganizationStatusChangeResult:
        self._ensure_superuser(actor)
        results: list[AdminBulkOrganizationStatusChangeItem] = []
        updated_count = 0

        for organization_id in organization_ids:
            try:
                if action == "suspend":
                    outcome = self.suspend_organization(
                        actor=actor,
                        organization_id=organization_id,
                        reason=reason,
                    )
                else:
                    outcome = self.reactivate_organization(
                        actor=actor,
                        organization_id=organization_id,
                        reason=reason,
                    )
            except CaseFlowError as exc:
                self.session.rollback()
                organization = self.session.get(Organization, organization_id)
                results.append(
                    AdminBulkOrganizationStatusChangeItem(
                        organization_id=organization_id,
                        organization_slug=organization.slug if organization is not None else None,
                        outcome="failed",
                        previous_status=organization.status if organization is not None else None,
                        current_status=organization.status if organization is not None else None,
                        revoked_auth_sessions=0,
                        error_code=exc.code,
                        error_message=exc.message,
                    )
                )
                continue

            updated_count += 1
            results.append(
                AdminBulkOrganizationStatusChangeItem(
                    organization_id=outcome.organization.id,
                    organization_slug=outcome.organization.slug,
                    outcome="updated",
                    previous_status=outcome.previous_status,
                    current_status=outcome.current_status,
                    revoked_auth_sessions=outcome.revoked_auth_sessions,
                    error_code=None,
                    error_message=None,
                )
            )

        return AdminBulkOrganizationStatusChangeResult(
            action=action,
            total_requested=len(organization_ids),
            updated_count=updated_count,
            failed_count=len(organization_ids) - updated_count,
            results=results,
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

    def _collect_anomalies(self) -> list[AdminAnomalyItem]:
        return [
            *self._detect_organizations_without_active_owner(),
            *self._detect_failed_job_anomalies(),
            *self._detect_failed_webhook_anomalies(),
            *self._detect_failed_email_anomalies(),
            *self._detect_stale_processing_queue_anomalies(),
            *self._detect_stale_webhook_queue_anomalies(),
            *self._detect_stale_email_queue_anomalies(),
            *self._detect_inactive_organization_api_key_anomalies(),
            *self._detect_inactive_organization_session_anomalies(),
        ]

    def _index_anomalies_by_organization(
        self,
        anomalies: list[AdminAnomalyItem],
    ) -> dict[UUID, list[AdminAnomalyItem]]:
        grouped: dict[UUID, list[AdminAnomalyItem]] = {}
        for anomaly in anomalies:
            grouped.setdefault(anomaly.organization_id, []).append(anomaly)
        for items in grouped.values():
            items.sort(
                key=lambda item: (
                    self._severity_rank(item.severity),
                    -item.detected_at.timestamp(),
                    item.code,
                )
            )
        return grouped

    def _build_risk_report_item(
        self,
        *,
        organization: AdminOrganizationListItem,
        anomalies: list[AdminAnomalyItem],
    ) -> AdminRiskReportItem:
        critical_count = sum(1 for item in anomalies if item.severity == "critical")
        warning_count = sum(1 for item in anomalies if item.severity == "warning")
        info_count = sum(1 for item in anomalies if item.severity == "info")
        risk_score = sum(self._anomaly_weight(item.severity) for item in anomalies)
        risk_level = self._risk_level_from_score(risk_score)
        return AdminRiskReportItem(
            organization_id=organization.organization.id,
            organization_name=organization.organization.name,
            organization_slug=organization.organization.slug,
            status=organization.organization.status,
            risk_score=risk_score,
            risk_level=risk_level,
            anomaly_count=len(anomalies),
            critical_anomaly_count=critical_count,
            warning_anomaly_count=warning_count,
            info_anomaly_count=info_count,
            top_anomaly_codes=[item.code for item in anomalies[:3]],
            active_members=organization.active_members,
            active_auth_sessions=organization.active_auth_sessions,
            open_cases=organization.open_cases,
            archived_cases=organization.archived_cases,
            failed_jobs=organization.failed_jobs,
            failed_webhook_deliveries=organization.failed_webhook_deliveries,
            failed_emails=organization.failed_emails,
            last_activity_at=organization.last_activity_at,
        )

    def _detect_organizations_without_active_owner(self) -> list[AdminAnomalyItem]:
        active_owner_count = (
            select(func.count(OrganizationMembership.id))
            .where(
                OrganizationMembership.organization_id == Organization.id,
                OrganizationMembership.role == OrganizationRole.OWNER,
                OrganizationMembership.is_active.is_(True),
            )
            .correlate(Organization)
            .scalar_subquery()
        )
        return [
            AdminAnomalyItem(
                organization_id=organization.id,
                organization_name=organization.name,
                organization_slug=organization.slug,
                severity="critical",
                code="organization_without_active_owner",
                summary="Organization has no active owner membership.",
                detected_at=datetime.now(UTC),
                metadata={"status": organization.status.value},
            )
            for organization in self.session.scalars(
                select(Organization).where(
                    Organization.status != OrganizationStatus.ARCHIVED,
                    active_owner_count == 0,
                )
            )
        ]

    def _detect_failed_job_anomalies(self) -> list[AdminAnomalyItem]:
        threshold = self.settings.admin_failure_anomaly_threshold
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(ProcessingJob.id),
                func.max(ProcessingJob.created_at),
            )
            .join(ProcessingJob, ProcessingJob.organization_id == Organization.id)
            .where(
                ProcessingJob.status.in_(
                    [ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTERED]
                )
            )
            .group_by(Organization.id, Organization.name, Organization.slug)
            .having(func.count(ProcessingJob.id) >= threshold)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="critical",
                code="organization_failed_jobs_threshold_exceeded",
                summary="Organization exceeded the failed processing jobs threshold.",
                detected_at=latest_failure_at,
                metadata={"failed_jobs": failed_jobs, "threshold": threshold},
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                failed_jobs,
                latest_failure_at,
            ) in rows
        ]

    def _detect_failed_webhook_anomalies(self) -> list[AdminAnomalyItem]:
        threshold = self.settings.admin_failure_anomaly_threshold
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(WebhookDelivery.id),
                func.max(WebhookDelivery.created_at),
            )
            .join(WebhookDelivery, WebhookDelivery.organization_id == Organization.id)
            .where(WebhookDelivery.status == WebhookDeliveryStatus.FAILED)
            .group_by(Organization.id, Organization.name, Organization.slug)
            .having(func.count(WebhookDelivery.id) >= threshold)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="warning",
                code="organization_failed_webhook_deliveries_threshold_exceeded",
                summary="Organization exceeded the failed webhook deliveries threshold.",
                detected_at=latest_failure_at,
                metadata={
                    "failed_webhook_deliveries": failed_deliveries,
                    "threshold": threshold,
                },
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                failed_deliveries,
                latest_failure_at,
            ) in rows
        ]

    def _detect_failed_email_anomalies(self) -> list[AdminAnomalyItem]:
        threshold = self.settings.admin_failure_anomaly_threshold
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(OutboundEmail.id),
                func.max(OutboundEmail.created_at),
            )
            .join(OutboundEmail, OutboundEmail.organization_id == Organization.id)
            .where(OutboundEmail.status == OutboundEmailStatus.FAILED)
            .group_by(Organization.id, Organization.name, Organization.slug)
            .having(func.count(OutboundEmail.id) >= threshold)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="warning",
                code="organization_failed_emails_threshold_exceeded",
                summary="Organization exceeded the failed outbound emails threshold.",
                detected_at=latest_failure_at,
                metadata={"failed_emails": failed_emails, "threshold": threshold},
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                failed_emails,
                latest_failure_at,
            ) in rows
        ]

    def _detect_stale_processing_queue_anomalies(self) -> list[AdminAnomalyItem]:
        stale_before = datetime.now(UTC) - timedelta(hours=self.settings.admin_queue_stale_hours)
        due_at = func.coalesce(ProcessingJob.next_retry_at, ProcessingJob.scheduled_at)
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(ProcessingJob.id),
                func.min(due_at),
            )
            .join(ProcessingJob, ProcessingJob.organization_id == Organization.id)
            .where(
                ProcessingJob.status.in_([ProcessingJobStatus.PENDING, ProcessingJobStatus.QUEUED]),
                due_at < stale_before,
            )
            .group_by(Organization.id, Organization.name, Organization.slug)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="warning",
                code="organization_stale_processing_queue",
                summary=(
                    "Organization has stale processing jobs waiting beyond the queue threshold."
                ),
                detected_at=oldest_due_at,
                metadata={
                    "queued_jobs": queued_jobs,
                    "stale_before": stale_before.isoformat(),
                },
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                queued_jobs,
                oldest_due_at,
            ) in rows
        ]

    def _detect_stale_webhook_queue_anomalies(self) -> list[AdminAnomalyItem]:
        stale_before = datetime.now(UTC) - timedelta(hours=self.settings.admin_queue_stale_hours)
        due_at = func.coalesce(WebhookDelivery.next_retry_at, WebhookDelivery.created_at)
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(WebhookDelivery.id),
                func.min(due_at),
            )
            .join(WebhookDelivery, WebhookDelivery.organization_id == Organization.id)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                due_at < stale_before,
            )
            .group_by(Organization.id, Organization.name, Organization.slug)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="warning",
                code="organization_stale_webhook_queue",
                summary=(
                    "Organization has stale webhook deliveries waiting beyond the queue threshold."
                ),
                detected_at=oldest_due_at,
                metadata={
                    "queued_webhook_deliveries": queued_deliveries,
                    "stale_before": stale_before.isoformat(),
                },
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                queued_deliveries,
                oldest_due_at,
            ) in rows
        ]

    def _detect_stale_email_queue_anomalies(self) -> list[AdminAnomalyItem]:
        stale_before = datetime.now(UTC) - timedelta(hours=self.settings.admin_queue_stale_hours)
        due_at = func.coalesce(OutboundEmail.next_retry_at, OutboundEmail.scheduled_at)
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(OutboundEmail.id),
                func.min(due_at),
            )
            .join(OutboundEmail, OutboundEmail.organization_id == Organization.id)
            .where(
                OutboundEmail.status == OutboundEmailStatus.PENDING,
                due_at < stale_before,
            )
            .group_by(Organization.id, Organization.name, Organization.slug)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="warning",
                code="organization_stale_email_queue",
                summary=(
                    "Organization has stale outbound emails waiting beyond the queue threshold."
                ),
                detected_at=oldest_due_at,
                metadata={
                    "queued_emails": queued_emails,
                    "stale_before": stale_before.isoformat(),
                },
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                queued_emails,
                oldest_due_at,
            ) in rows
        ]

    def _detect_inactive_organization_api_key_anomalies(self) -> list[AdminAnomalyItem]:
        now = datetime.now(UTC)
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(ApiKey.id),
                func.max(ApiKey.created_at),
            )
            .join(ApiKey, ApiKey.organization_id == Organization.id)
            .where(
                Organization.status != OrganizationStatus.ACTIVE,
                ApiKey.revoked_at.is_(None),
                or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > now),
            )
            .group_by(Organization.id, Organization.name, Organization.slug)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="warning",
                code="inactive_organization_with_active_api_keys",
                summary="Inactive organization still has active API keys.",
                detected_at=latest_api_key_created_at,
                metadata={"active_api_keys": active_api_keys},
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                active_api_keys,
                latest_api_key_created_at,
            ) in rows
        ]

    def _detect_inactive_organization_session_anomalies(self) -> list[AdminAnomalyItem]:
        now = datetime.now(UTC)
        rows = self.session.execute(
            select(
                Organization.id,
                Organization.name,
                Organization.slug,
                func.count(AuthSession.id),
                func.max(AuthSession.created_at),
            )
            .join(AuthSession, AuthSession.organization_id == Organization.id)
            .join(User, AuthSession.user_id == User.id)
            .join(
                OrganizationMembership,
                AuthSession.membership_id == OrganizationMembership.id,
            )
            .where(
                Organization.status != OrganizationStatus.ACTIVE,
                AuthSession.revoked_at.is_(None),
                AuthSession.refresh_token_expires_at > now,
                User.is_active.is_(True),
                OrganizationMembership.is_active.is_(True),
            )
            .group_by(Organization.id, Organization.name, Organization.slug)
        )
        return [
            AdminAnomalyItem(
                organization_id=organization_id,
                organization_name=organization_name,
                organization_slug=organization_slug,
                severity="critical",
                code="inactive_organization_with_active_auth_sessions",
                summary="Inactive organization still has active auth sessions.",
                detected_at=latest_session_created_at,
                metadata={"active_auth_sessions": active_auth_sessions},
            )
            for (
                organization_id,
                organization_name,
                organization_slug,
                active_auth_sessions,
                latest_session_created_at,
            ) in rows
        ]

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

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {"critical": 0, "warning": 1, "info": 2}.get(severity, 99)

    @staticmethod
    def _anomaly_weight(severity: str) -> int:
        return {"critical": 50, "warning": 20, "info": 5}.get(severity, 0)

    @classmethod
    def _risk_level_from_score(cls, score: int) -> str:
        if score >= 100:
            return "critical"
        if score >= 50:
            return "high"
        if score >= 20:
            return "medium"
        if score > 0:
            return "low"
        return "healthy"

    @staticmethod
    def _risk_level_rank(risk_level: str) -> int:
        return {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "healthy": 4,
        }.get(risk_level, 99)


def _serialize_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()
