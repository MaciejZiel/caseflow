"""Email delivery adapters."""

from __future__ import annotations

from typing import Protocol

from app.core.config import get_settings
from app.domain.emails.models import OutboundEmail
from app.infrastructure.email.local import LocalEmailSink
from app.infrastructure.email.smtp import SmtpEmailSink


class EmailDeliveryBackend(Protocol):
    def deliver(self, email: OutboundEmail) -> str: ...


def resolve_email_backend() -> EmailDeliveryBackend:
    settings = get_settings()
    if settings.email_delivery_backend == "smtp":
        return SmtpEmailSink()
    return LocalEmailSink()
