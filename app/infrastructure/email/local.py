"""Local file-based email sink for development and testing."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.domain.emails.models import OutboundEmail


class LocalEmailSink:
    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = (base_path or settings.local_email_sink_path).resolve()

    def deliver(self, email: OutboundEmail) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        self.base_path.mkdir(parents=True, exist_ok=True)
        path = self.base_path / f"{timestamp}_{email.id}.json"
        payload = {
            "email_id": str(email.id),
            "organization_id": str(email.organization_id) if email.organization_id else None,
            "template_key": email.template_key,
            "recipient_email": email.recipient_email,
            "subject": email.subject,
            "body_text": email.body_text,
            "payload": email.payload_json,
            "created_at": email.created_at.replace(tzinfo=UTC).isoformat()
            if email.created_at.tzinfo is None
            else email.created_at.astimezone(UTC).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return str(path)
