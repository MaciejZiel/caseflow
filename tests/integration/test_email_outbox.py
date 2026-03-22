from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.domain.emails.models import OutboundEmail
from app.infrastructure.db.session import get_session_factory
from app.workers.retries import run_retry_cycle
from tests.integration.helpers import create_invitation, register_owner


def _read_email_sink_files(email_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(email_dir.glob("*.json"))
    ]


@pytest.mark.asyncio
async def test_invitation_creation_writes_email_to_local_sink(
    async_client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    owner = await register_owner(async_client)

    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="invitee@example.com",
        role="reviewer",
    )

    email_payloads = _read_email_sink_files(tmp_path / "emails")
    assert len(email_payloads) == 1
    assert email_payloads[0]["recipient_email"] == "invitee@example.com"
    assert email_payloads[0]["template_key"] == "organization_invitation"
    assert invitation["invitation_token"] in email_payloads[0]["body_text"]


@pytest.mark.asyncio
async def test_password_reset_request_writes_email_and_token_can_be_used(
    async_client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    await async_client.post("/api/v1/auth/register", json={
        "organization_name": "Acme Claims",
        "organization_slug": "acme-claims",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "password": "StrongPass123",
    })

    reset_requested = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "ada@example.com"},
    )
    assert reset_requested.status_code == 202

    email_payloads = _read_email_sink_files(tmp_path / "emails")
    assert len(email_payloads) == 1
    reset_token = str(email_payloads[0]["payload"]["reset_token"])

    reset_confirmed = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "password": "NewStrongPass123"},
    )
    assert reset_confirmed.status_code == 200

    new_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "NewStrongPass123"},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_retry_worker_processes_failed_email_delivery(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    owner = await register_owner(async_client)

    should_fail = True

    def fake_deliver(self, email: OutboundEmail) -> str:
        if should_fail:
            raise RuntimeError("local sink unavailable")
        return str((tmp_path / "emails" / f"{email.id}.json").resolve())

    monkeypatch.setattr("app.infrastructure.email.local.LocalEmailSink.deliver", fake_deliver)

    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="retry-email@example.com",
        role="member",
    )
    assert invitation["invitation"]["email"] == "retry-email@example.com"

    session = get_session_factory()()
    try:
        email = session.scalar(
            select(OutboundEmail).where(OutboundEmail.recipient_email == "retry-email@example.com")
        )
        assert email is not None
        assert email.status.value == "failed"
        email.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        email_id = UUID(str(email.id))
    finally:
        session.close()

    should_fail = False
    retried = run_retry_cycle(limit_per_queue=10)
    assert retried.processed_emails == 1

    session = get_session_factory()()
    try:
        email = session.scalar(select(OutboundEmail).where(OutboundEmail.id == email_id))
        assert email is not None
        assert email.status.value == "sent"
        assert email.attempts == 2
        assert email.next_retry_at is None
    finally:
        session.close()
