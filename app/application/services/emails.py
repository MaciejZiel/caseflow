"""Outbound email outbox and delivery workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.emails.models import OutboundEmail, OutboundEmailStatus
from app.domain.organizations.models import Invitation, Organization
from app.domain.users.models import User
from app.infrastructure.email import EmailDeliveryBackend, resolve_email_backend


@dataclass(slots=True)
class OutboundEmailCreatePayload:
    organization_id: UUID | None
    template_key: str
    recipient_email: str
    subject: str
    body_text: str
    payload_json: dict[str, object]


class EmailOutboxService:
    def __init__(
        self,
        session: Session,
        *,
        sink: EmailDeliveryBackend | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.sink = sink or resolve_email_backend()

    def enqueue_invitation_email(
        self,
        *,
        invitation: Invitation,
        invitation_token: str,
        organization: Organization,
        invited_by_name: str,
    ) -> OutboundEmail:
        payload = OutboundEmailCreatePayload(
            organization_id=organization.id,
            template_key="organization_invitation",
            recipient_email=invitation.email,
            subject=f"You're invited to {organization.name} on CaseFlow",
            body_text=(
                f"Hello,\n\n"
                f"{invited_by_name} invited you to join {organization.name} "
                f"as {invitation.role.value}.\n"
                f"Invitation token: {invitation_token}\n"
                f"Invitation expires at: {_format_datetime(invitation.expires_at)}\n\n"
                f"Use this token to accept the invitation in CaseFlow."
            ),
            payload_json={
                "organization_slug": organization.slug,
                "role": invitation.role.value,
                "invitation_token": invitation_token,
                "expires_at": _format_datetime(invitation.expires_at),
            },
        )
        return self._create_outbound_email(payload)

    def enqueue_password_reset_email(
        self,
        *,
        user: User,
        reset_token: str,
        expires_at: datetime,
    ) -> OutboundEmail:
        payload = OutboundEmailCreatePayload(
            organization_id=None,
            template_key="password_reset",
            recipient_email=user.email,
            subject="Reset your CaseFlow password",
            body_text=(
                f"Hello {user.first_name},\n\n"
                f"We received a request to reset your CaseFlow password.\n"
                f"Reset token: {reset_token}\n"
                f"Token expires at: {_format_datetime(expires_at)}\n\n"
                f"If you did not request this change, you can ignore this message."
            ),
            payload_json={
                "reset_token": reset_token,
                "expires_at": _format_datetime(expires_at),
            },
        )
        return self._create_outbound_email(payload)

    def dispatch_emails(self, email_ids: list[UUID]) -> None:
        if not email_ids:
            return
        emails = list(
            self.session.scalars(
                select(OutboundEmail)
                .where(OutboundEmail.id.in_(email_ids))
                .order_by(OutboundEmail.created_at.asc())
            )
        )
        for email in emails:
            self._deliver_email(email)

    def dispatch_enqueued_emails(self, email_ids: list[UUID]) -> None:
        if self.settings.email_delivery_mode != "sync":
            return
        self.dispatch_emails(email_ids)

    def process_due_emails(
        self,
        *,
        limit: int = 100,
        organization_id: UUID | None = None,
    ) -> list[UUID]:
        now = datetime.now(UTC)
        query = select(OutboundEmail.id).where(
            or_(
                and_(
                    OutboundEmail.status == OutboundEmailStatus.PENDING,
                    OutboundEmail.scheduled_at <= now,
                ),
                and_(
                    OutboundEmail.status == OutboundEmailStatus.FAILED,
                    OutboundEmail.next_retry_at.is_not(None),
                    OutboundEmail.next_retry_at <= now,
                ),
            )
        )
        if organization_id is not None:
            query = query.where(OutboundEmail.organization_id == organization_id)
        email_ids = list(
            self.session.scalars(
                query.order_by(
                    func.coalesce(
                        OutboundEmail.next_retry_at,
                        OutboundEmail.scheduled_at,
                        OutboundEmail.created_at,
                    ).asc()
                ).limit(limit)
            )
        )
        self.dispatch_emails(email_ids)
        return email_ids

    def _create_outbound_email(self, payload: OutboundEmailCreatePayload) -> OutboundEmail:
        email = OutboundEmail(
            organization_id=payload.organization_id,
            template_key=payload.template_key,
            recipient_email=payload.recipient_email,
            subject=payload.subject,
            body_text=payload.body_text,
            payload_json=payload.payload_json,
        )
        self.session.add(email)
        return email

    def _deliver_email(self, email: OutboundEmail) -> None:
        email.attempts += 1
        email.next_retry_at = None
        email.last_error = None
        try:
            delivery_reference = self.sink.deliver(email)
        except Exception as exc:  # pragma: no cover - covered via monkeypatched integration tests
            email.status = OutboundEmailStatus.FAILED
            email.last_error = str(exc)[:1000]
            email.next_retry_at = datetime.now(UTC) + timedelta(
                seconds=self.settings.email_retry_base_delay_seconds
                * (2 ** max(email.attempts - 1, 0))
            )
            self.session.commit()
            return

        email.status = OutboundEmailStatus.SENT
        email.delivery_reference = delivery_reference
        email.sent_at = datetime.now(UTC)
        self.session.commit()


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()
