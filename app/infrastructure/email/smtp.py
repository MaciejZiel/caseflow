"""SMTP email delivery adapter."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from app.core.config import get_settings
from app.core.errors import DomainValidationError
from app.domain.emails.models import OutboundEmail


class SmtpEmailSink:
    def __init__(self) -> None:
        self.settings = get_settings()

    def deliver(self, email: OutboundEmail) -> str:
        if not self.settings.smtp_host:
            raise DomainValidationError(
                "smtp_host_missing",
                "SMTP_HOST must be configured when EMAIL_DELIVERY_BACKEND is smtp.",
            )

        message = EmailMessage()
        message["Subject"] = email.subject
        message["To"] = email.recipient_email
        message["From"] = self._build_from_header()
        message["Message-ID"] = make_msgid(domain=self.settings.smtp_from_email.split("@")[-1])
        message.set_content(email.body_text)

        client_cls = smtplib.SMTP_SSL if self.settings.smtp_use_ssl else smtplib.SMTP
        with client_cls(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=self.settings.smtp_timeout_seconds,
        ) as client:
            if self.settings.smtp_use_starttls and not self.settings.smtp_use_ssl:
                client.starttls()
            if self.settings.smtp_username:
                client.login(self.settings.smtp_username, self.settings.smtp_password or "")
            client.send_message(message)
        return str(message["Message-ID"])

    def _build_from_header(self) -> str:
        if self.settings.smtp_from_name:
            return f"{self.settings.smtp_from_name} <{self.settings.smtp_from_email}>"
        return self.settings.smtp_from_email
