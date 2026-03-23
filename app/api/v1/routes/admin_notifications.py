"""Platform admin notification routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import SuperuserActor, get_current_superuser_actor
from app.api.v1.schemas.admin_notifications import (
    AdminNotificationDigestPreviewResponse,
    AdminNotificationDigestSendResponse,
    AdminNotificationMarkAllReadResponse,
    AdminNotificationPreferenceResponse,
    AdminNotificationPreferenceUpdateRequest,
    AdminNotificationResponse,
    AdminNotificationSummaryResponse,
)
from app.api.v1.schemas.admin_reviews import (
    AdminReviewOrganizationResponse,
    AdminReviewUserResponse,
)
from app.application.services.admin_notifications import (
    AdminNotificationDigestPreview,
    AdminNotificationDigestSendResult,
    AdminNotificationItem,
    AdminNotificationPreferenceSnapshot,
    AdminNotificationService,
    AdminNotificationSummary,
)
from app.domain.admin_notifications.models import AdminNotificationType
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/admin/notifications")
SessionDep = Annotated[Session, Depends(get_db_session)]
SuperuserActorDep = Annotated[SuperuserActor, Depends(get_current_superuser_actor)]


@router.get("", response_model=list[AdminNotificationResponse])
async def list_notifications(
    actor: SuperuserActorDep,
    session: SessionDep,
    unread_only: bool = False,
    notification_type: AdminNotificationType | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminNotificationResponse]:
    notifications = AdminNotificationService(session).list_notifications(
        actor=actor,
        unread_only=unread_only,
        notification_type=notification_type,
        limit=limit,
        offset=offset,
    )
    return [_to_notification_response(item) for item in notifications]


@router.get("/summary", response_model=AdminNotificationSummaryResponse)
async def get_notification_summary(
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminNotificationSummaryResponse:
    summary = AdminNotificationService(session).get_summary(actor=actor)
    return _to_notification_summary_response(summary)


@router.get("/digest-preview", response_model=AdminNotificationDigestPreviewResponse)
async def preview_notification_digest(
    actor: SuperuserActorDep,
    session: SessionDep,
    unread_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminNotificationDigestPreviewResponse:
    preview = AdminNotificationService(session).preview_digest(
        actor=actor,
        unread_only=unread_only,
        limit=limit,
    )
    return _to_notification_digest_preview_response(preview)


@router.post("/send-digest", response_model=AdminNotificationDigestSendResponse)
async def send_notification_digest(
    actor: SuperuserActorDep,
    session: SessionDep,
    unread_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminNotificationDigestSendResponse:
    result = AdminNotificationService(session).send_digest(
        actor=actor,
        unread_only=unread_only,
        limit=limit,
    )
    return _to_notification_digest_send_response(result)


@router.get("/preferences", response_model=AdminNotificationPreferenceResponse)
async def get_notification_preferences(
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminNotificationPreferenceResponse:
    preference = AdminNotificationService(session).get_preferences(actor=actor)
    return _to_notification_preference_response(preference)


@router.patch("/preferences", response_model=AdminNotificationPreferenceResponse)
async def update_notification_preferences(
    payload: AdminNotificationPreferenceUpdateRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminNotificationPreferenceResponse:
    preference = AdminNotificationService(session).update_preferences(
        actor=actor,
        payload=payload,
    )
    return _to_notification_preference_response(preference)


@router.post("/{notification_id}/read", response_model=AdminNotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminNotificationResponse:
    notification = AdminNotificationService(session).mark_read(
        actor=actor,
        notification_id=notification_id,
    )
    return _to_notification_response(notification)


@router.post("/read-all", response_model=AdminNotificationMarkAllReadResponse)
async def mark_all_notifications_read(
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminNotificationMarkAllReadResponse:
    updated_count = AdminNotificationService(session).mark_all_read(actor=actor)
    return AdminNotificationMarkAllReadResponse(updated_count=updated_count)


def _to_notification_response(notification: AdminNotificationItem) -> AdminNotificationResponse:
    return AdminNotificationResponse(
        id=notification.id,
        notification_type=notification.notification_type,
        title=notification.title,
        body=notification.body,
        organization=(
            AdminReviewOrganizationResponse(
                id=notification.organization.id,
                name=notification.organization.name,
                slug=notification.organization.slug,
                status=notification.organization.status,
            )
            if notification.organization is not None
            else None
        ),
        review_id=notification.review_id,
        metadata=notification.metadata,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def _to_notification_summary_response(
    summary: AdminNotificationSummary,
) -> AdminNotificationSummaryResponse:
    return AdminNotificationSummaryResponse(
        unread_count=summary.unread_count,
        counts_by_type=summary.counts_by_type,
    )


def _to_notification_digest_preview_response(
    preview: AdminNotificationDigestPreview,
) -> AdminNotificationDigestPreviewResponse:
    return AdminNotificationDigestPreviewResponse(
        total_count=preview.total_count,
        unread_only=preview.unread_only,
        counts_by_type=preview.counts_by_type,
        notifications=[_to_notification_response(item) for item in preview.notifications],
    )


def _to_notification_digest_send_response(
    result: AdminNotificationDigestSendResult,
) -> AdminNotificationDigestSendResponse:
    return AdminNotificationDigestSendResponse(
        sent=result.sent,
        recipient_email=result.recipient_email,
        total_count=result.total_count,
        template_key=result.template_key,
    )


def _to_notification_preference_response(
    preference: AdminNotificationPreferenceSnapshot,
) -> AdminNotificationPreferenceResponse:
    return AdminNotificationPreferenceResponse(
        user=AdminReviewUserResponse(
            id=preference.user.id,
            email=preference.user.email,
            first_name=preference.user.first_name,
            last_name=preference.user.last_name,
        ),
        email_enabled=preference.email_enabled,
        notify_on_review_auto_opened=preference.notify_on_review_auto_opened,
        notify_on_review_overdue_escalated=preference.notify_on_review_overdue_escalated,
    )
