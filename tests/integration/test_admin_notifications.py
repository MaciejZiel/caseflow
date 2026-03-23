from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.application.services import webhooks as webhook_module
from app.domain.admin_notifications.models import (
    AdminNotificationPreference,
)
from app.domain.emails.models import OutboundEmail
from app.infrastructure.db.session import get_session_factory
from app.workers.retries import run_retry_cycle
from tests.integration.helpers import (
    configured_async_client,
    create_case,
    create_invitation,
    encode_document_content,
    promote_user_to_superuser,
    register_owner,
)


class _FakeWebhookResponse:
    def __init__(self, *, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> _FakeWebhookResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def read(self, limit: int = -1) -> bytes:
        if limit < 0:
            return self._body
        return self._body[:limit]


def _read_email_sink_files(email_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(email_dir.glob("*.json"))
    ]


async def _create_risky_tenant(
    async_client: httpx.AsyncClient,
    *,
    organization_name: str,
    organization_slug: str,
    email: str,
) -> dict[str, str]:
    tenant = await register_owner(
        async_client,
        organization_name=organization_name,
        organization_slug=organization_slug,
        email=email,
    )

    created_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
        json={
            "target_url": f"https://{organization_slug}.example.test/webhook",
            "signing_secret": f"{organization_slug}-webhook-secret-1234567890",
            "subscribed_event_types": ["case.created"],
        },
    )
    assert created_endpoint.status_code == 201

    case = await create_case(
        async_client,
        access_token=tenant["access_token"],
        title=f"{organization_name} risk case",
    )
    created_document = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
        json={
            "title": "Broken intake package",
            "document_type": "attachment",
            "original_filename": "broken.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"FAIL_PROCESSING broken payload"),
        },
    )
    assert created_document.status_code == 201

    invitation = await create_invitation(
        async_client,
        access_token=tenant["access_token"],
        email=f"member@{organization_slug}.example.com",
        role="member",
    )
    assert invitation["invitation"]["id"] is not None
    return tenant


@pytest.mark.asyncio
async def test_auto_open_notifications_create_feed_items_and_email(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def selective_email_deliver(self, email: OutboundEmail) -> str:
        email_dir = (tmp_path / "emails").resolve()
        if email.template_key == "organization_invitation":
            raise RuntimeError("smtp offline for invitation")
        email_dir.mkdir(parents=True, exist_ok=True)
        path = email_dir / f"{email.id}.json"
        path.write_text(
            json.dumps(
                {
                    "template_key": email.template_key,
                    "recipient_email": email.recipient_email,
                    "subject": email.subject,
                    "body_text": email.body_text,
                    "payload": email.payload_json,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return str(path)

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"ADMIN_FAILURE_ANOMALY_THRESHOLD": "1"},
    ) as async_client:
        monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
        monkeypatch.setattr(
            "app.infrastructure.email.local.LocalEmailSink.deliver",
            selective_email_deliver,
        )

        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        await _create_risky_tenant(
            async_client,
            organization_name="Notification Target",
            organization_slug="notification-target",
            email="owner@notification-target.example.com",
        )

        auto_open = await async_client.post(
            "/api/v1/admin/reviews/auto-open",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"min_risk_score": 50, "limit": 10},
        )
        assert auto_open.status_code == 200
        assert auto_open.json()["created_count"] == 1

        summary = await async_client.get(
            "/api/v1/admin/notifications/summary",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert summary.status_code == 200
        assert summary.json()["unread_count"] == 1
        assert summary.json()["counts_by_type"]["review_auto_opened"] == 1

        notifications = await async_client.get(
            "/api/v1/admin/notifications",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert notifications.status_code == 200
        notification_body = notifications.json()
        assert len(notification_body) == 1
        assert notification_body[0]["notification_type"] == "review_auto_opened"
        assert notification_body[0]["organization"]["slug"] == "notification-target"
        assert notification_body[0]["read_at"] is None

        email_payloads = _read_email_sink_files(tmp_path / "emails")
        notification_emails = [
            payload
            for payload in email_payloads
            if payload["template_key"] == "platform_review_auto_opened"
        ]
        assert len(notification_emails) == 1
        assert notification_emails[0]["recipient_email"] == admin["email"]


@pytest.mark.asyncio
async def test_notification_preferences_can_disable_auto_open_notifications(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def selective_email_deliver(self, email: OutboundEmail) -> str:
        if email.template_key == "organization_invitation":
            raise RuntimeError("smtp offline for invitation")
        email_dir = (tmp_path / "emails").resolve()
        email_dir.mkdir(parents=True, exist_ok=True)
        path = email_dir / f"{email.id}.json"
        path.write_text(
            json.dumps(
                {
                    "template_key": email.template_key,
                    "recipient_email": email.recipient_email,
                }
            ),
            encoding="utf-8",
        )
        return str(path)

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"ADMIN_FAILURE_ANOMALY_THRESHOLD": "1"},
    ) as async_client:
        monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
        monkeypatch.setattr(
            "app.infrastructure.email.local.LocalEmailSink.deliver",
            selective_email_deliver,
        )

        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        updated_preferences = await async_client.patch(
            "/api/v1/admin/notifications/preferences",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={
                "email_enabled": False,
                "notify_on_review_auto_opened": False,
            },
        )
        assert updated_preferences.status_code == 200
        assert updated_preferences.json()["email_enabled"] is False
        assert updated_preferences.json()["notify_on_review_auto_opened"] is False
        assert updated_preferences.json()["digest_schedule"] == "disabled"
        assert updated_preferences.json()["digest_next_due_at"] is None
        assert updated_preferences.json()["digest_last_sent_at"] is None

        await _create_risky_tenant(
            async_client,
            organization_name="Muted Notification Target",
            organization_slug="muted-notification-target",
            email="owner@muted-notification-target.example.com",
        )

        auto_open = await async_client.post(
            "/api/v1/admin/reviews/auto-open",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"min_risk_score": 50, "limit": 10},
        )
        assert auto_open.status_code == 200
        assert auto_open.json()["created_count"] == 1

        notifications = await async_client.get(
            "/api/v1/admin/notifications",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert notifications.status_code == 200
        assert notifications.json() == []
        assert _read_email_sink_files(tmp_path / "emails") == []


@pytest.mark.asyncio
async def test_overdue_escalation_notifications_can_be_marked_read(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with configured_async_client(tmp_path, monkeypatch) as async_client:
        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        tenant = await register_owner(
            async_client,
            organization_name="Escalation Notify Tenant",
            organization_slug="escalation-notify-tenant",
            email="owner@escalation-notify.example.com",
        )

        created_review = await async_client.post(
            f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={
                "title": "Escalate me",
                "due_at": "2024-01-10T09:00:00Z",
            },
        )
        assert created_review.status_code == 201

        escalated = await async_client.post(
            "/api/v1/admin/reviews/escalate-overdue",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"min_days_overdue": 1, "limit": 10},
        )
        assert escalated.status_code == 200
        assert escalated.json()["escalated_count"] == 1

        notifications = await async_client.get(
            "/api/v1/admin/notifications",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert notifications.status_code == 200
        notification = notifications.json()[0]
        assert notification["notification_type"] == "review_overdue_escalated"
        assert notification["read_at"] is None

        marked = await async_client.post(
            f"/api/v1/admin/notifications/{notification['id']}/read",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert marked.status_code == 200
        assert marked.json()["read_at"] is not None

        mark_all = await async_client.post(
            "/api/v1/admin/notifications/read-all",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert mark_all.status_code == 200
        assert mark_all.json()["updated_count"] == 0


@pytest.mark.asyncio
async def test_notification_digest_preview_and_send_use_existing_feed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def selective_email_deliver(self, email: OutboundEmail) -> str:
        if email.template_key == "organization_invitation":
            raise RuntimeError("smtp offline for invitation")
        email_dir = (tmp_path / "emails").resolve()
        email_dir.mkdir(parents=True, exist_ok=True)
        path = email_dir / f"{email.id}.json"
        path.write_text(
            json.dumps(
                {
                    "template_key": email.template_key,
                    "recipient_email": email.recipient_email,
                    "subject": email.subject,
                    "body_text": email.body_text,
                    "payload": email.payload_json,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return str(path)

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"ADMIN_FAILURE_ANOMALY_THRESHOLD": "1"},
    ) as async_client:
        monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
        monkeypatch.setattr(
            "app.infrastructure.email.local.LocalEmailSink.deliver",
            selective_email_deliver,
        )

        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        await _create_risky_tenant(
            async_client,
            organization_name="Digest Target",
            organization_slug="digest-target",
            email="owner@digest-target.example.com",
        )

        auto_open = await async_client.post(
            "/api/v1/admin/reviews/auto-open",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"min_risk_score": 50, "limit": 10},
        )
        assert auto_open.status_code == 200

        preview = await async_client.get(
            "/api/v1/admin/notifications/digest-preview",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"unread_only": "true", "limit": 10},
        )
        assert preview.status_code == 200
        preview_body = preview.json()
        assert preview_body["total_count"] == 1
        assert preview_body["unread_only"] is True
        assert preview_body["counts_by_type"]["review_auto_opened"] == 1
        assert len(preview_body["notifications"]) == 1

        sent = await async_client.post(
            "/api/v1/admin/notifications/send-digest",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"unread_only": "true", "limit": 10},
        )
        assert sent.status_code == 200
        sent_body = sent.json()
        assert sent_body["sent"] is True
        assert sent_body["recipient_email"] == admin["email"]
        assert sent_body["template_key"] == "platform_admin_notification_digest"

        email_payloads = _read_email_sink_files(tmp_path / "emails")
        digest_emails = [
            payload
            for payload in email_payloads
            if payload["template_key"] == "platform_admin_notification_digest"
        ]
        assert len(digest_emails) == 1
        assert "notification digest" in digest_emails[0]["subject"].lower()


@pytest.mark.asyncio
async def test_notification_digest_send_returns_not_sent_when_feed_is_empty(
    async_client: httpx.AsyncClient,
) -> None:
    admin = await register_owner(
        async_client,
        organization_name="Platform Admins",
        organization_slug="platform-admins",
        email="root@example.com",
    )
    promote_user_to_superuser(email=admin["email"])

    sent = await async_client.post(
        "/api/v1/admin/notifications/send-digest",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        params={"unread_only": "true", "limit": 10},
    )
    assert sent.status_code == 200
    assert sent.json() == {
        "sent": False,
        "recipient_email": admin["email"],
        "total_count": 0,
        "template_key": None,
    }


@pytest.mark.asyncio
async def test_scheduled_notification_digest_is_processed_by_retry_worker(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def selective_email_deliver(self, email: OutboundEmail) -> str:
        email_dir = (tmp_path / "emails").resolve()
        email_dir.mkdir(parents=True, exist_ok=True)
        path = email_dir / f"{email.id}.json"
        path.write_text(
            json.dumps(
                {
                    "template_key": email.template_key,
                    "recipient_email": email.recipient_email,
                    "subject": email.subject,
                    "payload": email.payload_json,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return str(path)

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={
            "ADMIN_FAILURE_ANOMALY_THRESHOLD": "1",
            "EMAIL_DELIVERY_MODE": "worker",
        },
    ) as async_client:
        monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
        monkeypatch.setattr(
            "app.infrastructure.email.local.LocalEmailSink.deliver",
            selective_email_deliver,
        )

        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        updated_preferences = await async_client.patch(
            "/api/v1/admin/notifications/preferences",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"digest_schedule": "daily"},
        )
        assert updated_preferences.status_code == 200
        assert updated_preferences.json()["digest_schedule"] == "daily"
        assert updated_preferences.json()["digest_next_due_at"] is not None
        assert updated_preferences.json()["digest_last_sent_at"] is None

        await _create_risky_tenant(
            async_client,
            organization_name="Scheduled Digest Target",
            organization_slug="scheduled-digest-target",
            email="owner@scheduled-digest-target.example.com",
        )

        auto_open = await async_client.post(
            "/api/v1/admin/reviews/auto-open",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"min_risk_score": 50, "limit": 10},
        )
        assert auto_open.status_code == 200
        assert auto_open.json()["created_count"] == 1

        session = get_session_factory()()
        try:
            preference = session.scalar(
                select(AdminNotificationPreference).where(
                    AdminNotificationPreference.user_id == UUID(admin["user_id"])
                )
            )
            assert preference is not None
            preference.digest_next_due_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        finally:
            session.close()

        result = run_retry_cycle(limit_per_queue=10)
        assert result.processed_admin_notification_digests == 1
        assert result.processed_emails == 3

        refreshed_preferences = await async_client.get(
            "/api/v1/admin/notifications/preferences",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert refreshed_preferences.status_code == 200
        preference_body = refreshed_preferences.json()
        assert preference_body["digest_schedule"] == "daily"
        assert preference_body["digest_last_sent_at"] is not None
        assert preference_body["digest_next_due_at"] is not None

        email_payloads = _read_email_sink_files(tmp_path / "emails")
        digest_emails = [
            payload
            for payload in email_payloads
            if payload["template_key"] == "platform_admin_notification_digest"
        ]
        assert len(digest_emails) == 1
        assert digest_emails[0]["recipient_email"] == admin["email"]
        assert digest_emails[0]["payload"]["counts_by_type"]["review_auto_opened"] == 1
