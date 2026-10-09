"""Platform admin notification feed and preference services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    AdminNotificationDigestSchedule,
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
class AdminNotificationDigestPreview:
    total_count: int
    unread_only: bool
    counts_by_type: dict[str, int]
    notifications: list[AdminNotificationItem]


@dataclass(slots=True)
class AdminNotificationDigestSendResult:
    sent: bool
    recipient_email: str
    total_count: int
    template_key: str | None


@dataclass(slots=True)
class AdminNotificationPreferenceSnapshot:
    user: AdminReviewUserRef
    email_enabled: bool
    notify_on_review_auto_opened: bool
    notify_on_review_overdue_escalated: bool
    digest_schedule: AdminNotificationDigestSchedule
    digest_next_due_at: datetime | None
    digest_last_sent_at: datetime | None


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
        notifications = self._list_notification_models_for_user(
            user_id=actor.user.id,
            unread_only=unread_only,
            notification_type=notification_type,
            limit=limit,
            offset=offset,
        )
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

    def preview_digest(
        self,
        *,
        actor: ActorContext,
        unread_only: bool,
        limit: int,
    ) -> AdminNotificationDigestPreview:
        self._ensure_superuser(actor)
        return self._preview_digest_for_user(
            user=actor.user,
            unread_only=unread_only,
            limit=limit,
            created_after=None,
        )

    def send_digest(
        self,
        *,
        actor: ActorContext,
        unread_only: bool,
        limit: int,
    ) -> AdminNotificationDigestSendResult:
        self._ensure_superuser(actor)
        preview = self._preview_digest_for_user(
            user=actor.user,
            unread_only=unread_only,
            limit=limit,
            created_after=None,
        )
        if preview.total_count == 0:
            return AdminNotificationDigestSendResult(
                sent=False,
                recipient_email=actor.user.email,
                total_count=0,
                template_key=None,
            )

        now = datetime.now(UTC)
        email = self._enqueue_digest_email(
            organization_id=actor.organization.id,
            recipient_email=actor.user.email,
            unread_only=unread_only,
            preview=preview,
        )
        preference = self.session.scalar(
            select(AdminNotificationPreference).where(
                AdminNotificationPreference.user_id == actor.user.id
            )
        )
        if (
            preference is not None
            and preference.digest_schedule != AdminNotificationDigestSchedule.DISABLED
        ):
            preference.digest_last_sent_at = now
            preference.digest_next_due_at = self._build_next_digest_due_at(
                schedule=preference.digest_schedule,
                reference_time=now,
            )
        self.session.commit()
        self.email_outbox.dispatch_enqueued_emails([email.id])
        return AdminNotificationDigestSendResult(
            sent=True,
            recipient_email=actor.user.email,
            total_count=preview.total_count,
            template_key="platform_admin_notification_digest",
        )

    def process_due_digests(
        self,
        *,
        limit: int = 25,
        unread_only: bool = True,
        notification_limit: int = 50,
    ) -> int:
        now = datetime.now(UTC)
        due_preferences = list(
            self.session.execute(
                select(AdminNotificationPreference, User)
                .join(User, AdminNotificationPreference.user_id == User.id)
                .where(
                    User.is_superuser.is_(True),
                    User.is_active.is_(True),
                    AdminNotificationPreference.email_enabled.is_(True),
                    AdminNotificationPreference.digest_schedule
                    != AdminNotificationDigestSchedule.DISABLED,
                    AdminNotificationPreference.digest_next_due_at.is_not(None),
                    AdminNotificationPreference.digest_next_due_at <= now,
                )
                .order_by(
                    AdminNotificationPreference.digest_next_due_at.asc(),
                    User.created_at.asc(),
                )
                .limit(limit)
            )
        )
        if not due_preferences:
            return 0

        email_ids: list[UUID] = []
        sent_digests = 0
        for preference, user in due_preferences:
            preview = self._preview_digest_for_user(
                user=user,
                unread_only=unread_only,
                limit=notification_limit,
                created_after=preference.digest_last_sent_at,
            )
            preference.digest_next_due_at = self._build_next_digest_due_at(
                schedule=preference.digest_schedule,
                reference_time=now,
            )
            if preview.total_count == 0:
                continue
            email = self._enqueue_digest_email(
                organization_id=None,
                recipient_email=user.email,
                unread_only=unread_only,
                preview=preview,
            )
            preference.digest_last_sent_at = now
            self.session.flush()
            email_ids.append(email.id)
            sent_digests += 1

        self.session.commit()
        self.email_outbox.dispatch_enqueued_emails(email_ids)
        return sent_digests

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
        now = datetime.now(UTC)
        for field_name in payload.model_fields_set:
            setattr(preference, field_name, getattr(payload, field_name))
        if "digest_schedule" in payload.model_fields_set:
            preference.digest_next_due_at = self._build_next_digest_due_at(
                schedule=preference.digest_schedule,
                reference_time=now,
            )
        elif (
            "email_enabled" in payload.model_fields_set
            and preference.email_enabled
            and preference.digest_schedule != AdminNotificationDigestSchedule.DISABLED
            and preference.digest_next_due_at is None
        ):
            preference.digest_next_due_at = self._build_next_digest_due_at(
                schedule=preference.digest_schedule,
                reference_time=now,
            )
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
            digest_schedule=AdminNotificationDigestSchedule.DISABLED,
            digest_next_due_at=None,
            digest_last_sent_at=None,
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
            digest_schedule=AdminNotificationDigestSchedule.DISABLED,
            digest_next_due_at=None,
            digest_last_sent_at=None,
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
            digest_schedule=preference.digest_schedule,
            digest_next_due_at=preference.digest_next_due_at,
            digest_last_sent_at=preference.digest_last_sent_at,
        )

    def _preview_digest_for_user(
        self,
        *,
        user: User,
        unread_only: bool,
        limit: int,
        created_after: datetime | None,
    ) -> AdminNotificationDigestPreview:
        notifications = self._build_notification_items(
            self._list_notification_models_for_user(
                user_id=user.id,
                unread_only=unread_only,
                notification_type=None,
                limit=limit,
                offset=0,
                created_after=created_after,
            )
        )
        counts_by_type = {notification_type.value: 0 for notification_type in AdminNotificationType}
        for notification in notifications:
            counts_by_type[notification.notification_type.value] += 1
        return AdminNotificationDigestPreview(
            total_count=len(notifications),
            unread_only=unread_only,
            counts_by_type=counts_by_type,
            notifications=notifications,
        )

    def _list_notification_models_for_user(
        self,
        *,
        user_id: UUID,
        unread_only: bool,
        notification_type: AdminNotificationType | None,
        limit: int,
        offset: int,
        created_after: datetime | None = None,
    ) -> list[AdminNotification]:
        query = (
            select(AdminNotification)
            .where(AdminNotification.user_id == user_id)
            .order_by(AdminNotification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if unread_only:
            query = query.where(AdminNotification.read_at.is_(None))
        if notification_type is not None:
            query = query.where(AdminNotification.notification_type == notification_type)
        if created_after is not None:
            query = query.where(AdminNotification.created_at > created_after)
        return list(self.session.scalars(query))

    def _enqueue_digest_email(
        self,
        *,
        organization_id: UUID | None,
        recipient_email: str,
        unread_only: bool,
        preview: AdminNotificationDigestPreview,
    ):
        lines = [
            f"- {notification.created_at.isoformat()} [{notification.notification_type.value}] "
            f"{notification.title}"
            for notification in preview.notifications
        ]
        return self.email_outbox.enqueue_platform_admin_notification_email(
            organization_id=organization_id,
            recipient_email=recipient_email,
            template_key="platform_admin_notification_digest",
            subject="CaseFlow platform admin notification digest",
            body_text=(
                "Platform admin notification digest\n\n"
                f"Unread only: {'yes' if unread_only else 'no'}\n"
                f"Included notifications: {preview.total_count}\n\n" + "\n".join(lines)
            ),
            payload_json={
                "unread_only": unread_only,
                "total_count": preview.total_count,
                "counts_by_type": preview.counts_by_type,
                "notification_ids": [
                    str(notification.id) for notification in preview.notifications
                ],
            },
        )

    @staticmethod
    def _build_next_digest_due_at(
        *,
        schedule: AdminNotificationDigestSchedule,
        reference_time: datetime,
    ) -> datetime | None:
        if schedule == AdminNotificationDigestSchedule.DISABLED:
            return None
        delta_by_schedule = {
            AdminNotificationDigestSchedule.HOURLY: timedelta(hours=1),
            AdminNotificationDigestSchedule.DAILY: timedelta(days=1),
            AdminNotificationDigestSchedule.WEEKLY: timedelta(days=7),
        }
        return reference_time + delta_by_schedule[schedule]

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
