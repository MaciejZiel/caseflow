"""Platform admin notification feed and preference services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.admin_notifications import AdminNotificationPreferenceUpdateRequest
from app.application.actors import ActorContext
from app.application.services.admin_reviews import (
    AdminReviewDetail,
    AdminReviewOrganizationRef,
    AdminReviewUserRef,
)
from app.application.services.emails import EmailOutboxService
from app.core.errors import NotFoundError, PermissionDeniedError
from app.domain.admin_notifications.models import (
    AdminNotification,
    AdminNotificationPreference,
    AdminNotificationType,
)
from app.domain.users.models import User


@dataclass(slots=True)
class AdminNotificationItem:
    id: UUID
    notification_type: AdminNotificationType
    title: str
    body: str
    organization: AdminReviewOrganizationRef | None
    review_id: UUID | None
    metadata: dict[str, object]
    read_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class AdminNotificationSummary:
    unread_count: int
    counts_by_type: dict[str, int]


@dataclass(slots=True)
class AdminNotificationPreferenceSnapshot:
    user: AdminReviewUserRef
    email_enabled: bool
    notify_on_review_auto_opened: bool
    notify_on_review_overdue_escalated: bool


class AdminNotificationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.email_outbox = EmailOutboxService(session)

    def list_notifications(
        self,
        *,
        actor: ActorContext,
        unread_only: bool,
        notification_type: AdminNotificationType | None,
        limit: int,
        offset: int,
    ) -> list[AdminNotificationItem]:
        self._ensure_superuser(actor)
        query = (
            select(AdminNotification)
            .where(AdminNotification.user_id == actor.user.id)
            .order_by(AdminNotification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if unread_only:
            query = query.where(AdminNotification.read_at.is_(None))
        if notification_type is not None:
            query = query.where(AdminNotification.notification_type == notification_type)
        notifications = list(self.session.scalars(query))
        return self._build_notification_items(notifications)

    def get_summary(self, *, actor: ActorContext) -> AdminNotificationSummary:
        self._ensure_superuser(actor)
        unread_count = int(
            self.session.scalar(
                select(func.count(AdminNotification.id)).where(
                    AdminNotification.user_id == actor.user.id,
                    AdminNotification.read_at.is_(None),
                )
            )
            or 0
        )
        counts_by_type = {notification_type.value: 0 for notification_type in AdminNotificationType}
        for notification_type, count in self.session.execute(
            select(AdminNotification.notification_type, func.count(AdminNotification.id))
            .where(AdminNotification.user_id == actor.user.id)
            .group_by(AdminNotification.notification_type)
        ):
            counts_by_type[notification_type.value] = count
        return AdminNotificationSummary(
            unread_count=unread_count,
            counts_by_type=counts_by_type,
        )

    def get_preferences(self, *, actor: ActorContext) -> AdminNotificationPreferenceSnapshot:
        self._ensure_superuser(actor)
        preference = self._get_or_build_preference(actor.user)
        return self._build_preference_snapshot(user=actor.user, preference=preference)

    def update_preferences(
        self,
        *,
        actor: ActorContext,
        payload: AdminNotificationPreferenceUpdateRequest,
    ) -> AdminNotificationPreferenceSnapshot:
        self._ensure_superuser(actor)
        preference = self._get_or_create_preference(actor.user)
        for field_name in payload.model_fields_set:
            setattr(preference, field_name, getattr(payload, field_name))
        self.session.commit()
        return self._build_preference_snapshot(user=actor.user, preference=preference)

    def mark_read(
        self,
        *,
        actor: ActorContext,
        notification_id: UUID,
    ) -> AdminNotificationItem:
        self._ensure_superuser(actor)
        notification = self.session.scalar(
            select(AdminNotification).where(
                AdminNotification.id == notification_id,
                AdminNotification.user_id == actor.user.id,
            )
        )
        if notification is None:
            raise NotFoundError("admin_notification", "Platform notification does not exist.")
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            self.session.commit()
        return self._build_notification_items([notification])[0]

    def mark_all_read(self, *, actor: ActorContext) -> int:
        self._ensure_superuser(actor)
        notifications = list(
            self.session.scalars(
                select(AdminNotification).where(
                    AdminNotification.user_id == actor.user.id,
                    AdminNotification.read_at.is_(None),
                )
            )
        )
        now = datetime.now(UTC)
        for notification in notifications:
            notification.read_at = now
        if notifications:
            self.session.commit()
        return len(notifications)

    def notify_review_auto_opened(
        self,
        *,
        actor: ActorContext,
        review: AdminReviewDetail,
    ) -> None:
        self._ensure_superuser(actor)
        recipients = self._list_notifiable_superusers()
        email_ids: list[UUID] = []
        for user in recipients:
            preference = self._get_or_build_preference(user)
            if not preference.notify_on_review_auto_opened:
                continue
            notification = AdminNotification(
                user_id=user.id,
                organization_id=review.organization.id,
                review_id=review.id,
                notification_type=AdminNotificationType.REVIEW_AUTO_OPENED,
                title=f"Platform review auto-opened for {review.organization.name}",
                body=(
                    f"{review.title}. Risk score {review.risk_score_snapshot}, "
                    f"risk level {review.risk_level_snapshot}."
                ),
                metadata_json={
                    "organization_slug": review.organization.slug,
                    "risk_score": review.risk_score_snapshot,
                    "risk_level": review.risk_level_snapshot,
                    "top_anomaly_codes": review.top_anomaly_codes_snapshot,
                },
            )
            self.session.add(notification)
            self.session.flush()
            if preference.email_enabled:
                email = self.email_outbox.enqueue_platform_admin_notification_email(
                    organization_id=review.organization.id,
                    recipient_email=user.email,
                    template_key="platform_review_auto_opened",
                    subject=f"Platform review auto-opened: {review.organization.name}",
                    body_text=(
                        f"Platform review {review.title} was opened for "
                        f"{review.organization.name}.\n\n"
                        f"Risk score: {review.risk_score_snapshot}\n"
                        f"Risk level: {review.risk_level_snapshot}\n"
                        f"Top anomaly codes: {', '.join(review.top_anomaly_codes_snapshot)}"
                    ),
                    payload_json={
                        "review_id": str(review.id),
                        "organization_slug": review.organization.slug,
                        "risk_score": review.risk_score_snapshot,
                        "risk_level": review.risk_level_snapshot,
                        "notification_type": AdminNotificationType.REVIEW_AUTO_OPENED.value,
                    },
                )
                self.session.flush()
                email_ids.append(email.id)
        if recipients:
            self.session.commit()
            self.email_outbox.dispatch_enqueued_emails(email_ids)

    def notify_review_overdue_escalated(
        self,
        *,
        actor: ActorContext,
        review: AdminReviewDetail,
        days_overdue: int,
    ) -> None:
        self._ensure_superuser(actor)
        recipients = self._list_notifiable_superusers()
        email_ids: list[UUID] = []
        for user in recipients:
            preference = self._get_or_build_preference(user)
            if not preference.notify_on_review_overdue_escalated:
                continue
            notification = AdminNotification(
                user_id=user.id,
                organization_id=review.organization.id,
                review_id=review.id,
                notification_type=AdminNotificationType.REVIEW_OVERDUE_ESCALATED,
                title=f"Overdue platform review escalated for {review.organization.name}",
                body=(
                    f"{review.title} was escalated after {days_overdue} overdue day(s). "
                    f"Priority is now {review.priority.value}."
                ),
                metadata_json={
                    "organization_slug": review.organization.slug,
                    "days_overdue": days_overdue,
                    "priority": review.priority.value,
                    "notification_type": AdminNotificationType.REVIEW_OVERDUE_ESCALATED.value,
                },
            )
            self.session.add(notification)
            self.session.flush()
            if preference.email_enabled:
                email = self.email_outbox.enqueue_platform_admin_notification_email(
                    organization_id=review.organization.id,
                    recipient_email=user.email,
                    template_key="platform_review_overdue_escalated",
                    subject=f"Overdue platform review escalated: {review.organization.name}",
                    body_text=(
                        f"Platform review {review.title} for {review.organization.name} "
                        f"was escalated after {days_overdue} overdue day(s).\n\n"
                        f"Current priority: {review.priority.value}\n"
                        "Assigned to: "
                        f"{review.assigned_to.email if review.assigned_to else 'unassigned'}"
                    ),
                    payload_json={
                        "review_id": str(review.id),
                        "organization_slug": review.organization.slug,
                        "days_overdue": days_overdue,
                        "priority": review.priority.value,
                        "notification_type": AdminNotificationType.REVIEW_OVERDUE_ESCALATED.value,
                    },
                )
                self.session.flush()
                email_ids.append(email.id)
        if recipients:
            self.session.commit()
            self.email_outbox.dispatch_enqueued_emails(email_ids)

    def _build_notification_items(
        self,
        notifications: list[AdminNotification],
    ) -> list[AdminNotificationItem]:
        if not notifications:
            return []
        organization_ids = {
            notification.organization_id
            for notification in notifications
            if notification.organization_id is not None
        }
        organizations = self._load_organizations(organization_ids)
        return [
            AdminNotificationItem(
                id=notification.id,
                notification_type=notification.notification_type,
                title=notification.title,
                body=notification.body,
                organization=organizations.get(notification.organization_id),
                review_id=notification.review_id,
                metadata=dict(notification.metadata_json or {}),
                read_at=notification.read_at,
                created_at=notification.created_at,
            )
            for notification in notifications
        ]

    def _list_notifiable_superusers(self) -> list[User]:
        return list(
            self.session.scalars(
                select(User)
                .where(
                    User.is_superuser.is_(True),
                    User.is_active.is_(True),
                )
                .order_by(User.created_at.asc())
            )
        )

    def _get_or_build_preference(self, user: User) -> AdminNotificationPreference:
        preference = self.session.scalar(
            select(AdminNotificationPreference).where(
                AdminNotificationPreference.user_id == user.id
            )
        )
        if preference is not None:
            return preference
        return AdminNotificationPreference(
            user_id=user.id,
            email_enabled=True,
            notify_on_review_auto_opened=True,
            notify_on_review_overdue_escalated=True,
        )

    def _get_or_create_preference(self, user: User) -> AdminNotificationPreference:
        preference = self.session.scalar(
            select(AdminNotificationPreference).where(
                AdminNotificationPreference.user_id == user.id
            )
        )
        if preference is not None:
            return preference
        preference = AdminNotificationPreference(
            user_id=user.id,
            email_enabled=True,
            notify_on_review_auto_opened=True,
            notify_on_review_overdue_escalated=True,
        )
        self.session.add(preference)
        self.session.flush()
        return preference

    @staticmethod
    def _build_preference_snapshot(
        *,
        user: User,
        preference: AdminNotificationPreference,
    ) -> AdminNotificationPreferenceSnapshot:
        return AdminNotificationPreferenceSnapshot(
            user=AdminReviewUserRef(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
            ),
            email_enabled=preference.email_enabled,
            notify_on_review_auto_opened=preference.notify_on_review_auto_opened,
            notify_on_review_overdue_escalated=preference.notify_on_review_overdue_escalated,
        )

    def _load_organizations(
        self,
        organization_ids: set[UUID],
    ) -> dict[UUID, AdminReviewOrganizationRef]:
        if not organization_ids:
            return {}
        from app.domain.organizations.models import Organization

        return {
            organization_id: AdminReviewOrganizationRef(
                id=organization_id,
                name=name,
                slug=slug,
                status=status,
            )
            for organization_id, name, slug, status in self.session.execute(
                select(
                    Organization.id,
                    Organization.name,
                    Organization.slug,
                    Organization.status,
                ).where(Organization.id.in_(organization_ids))
            )
        }

    @staticmethod
    def _ensure_superuser(actor: ActorContext) -> None:
        if not actor.user.is_superuser:
            raise PermissionDeniedError("Only platform admins can access admin notifications.")
