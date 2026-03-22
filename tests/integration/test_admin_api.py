from __future__ import annotations

from typing import Any
from urllib import error

import httpx
import pytest

from app.application.services import webhooks as webhook_module
from app.infrastructure.email.local import LocalEmailSink
from tests.integration.helpers import (
    accept_invitation,
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


@pytest.mark.asyncio
async def test_platform_admin_can_list_and_inspect_organizations(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def failing_email_deliver(self, email) -> str:
        raise RuntimeError("smtp offline")

    monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
    monkeypatch.setattr(LocalEmailSink, "deliver", failing_email_deliver)

    admin = await register_owner(
        async_client,
        organization_name="Platform Admins",
        organization_slug="platform-admins",
        email="root@example.com",
    )
    promote_user_to_superuser(email=admin["email"])

    tenant = await register_owner(
        async_client,
        organization_name="Beta Claims",
        organization_slug="beta-claims",
        email="owner@beta.example.com",
    )

    created_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
        json={
            "target_url": "https://beta.example.test/webhook",
            "signing_secret": "beta-webhook-secret-1234567890",
            "subscribed_event_types": ["case.created"],
        },
    )
    assert created_endpoint.status_code == 201

    case = await create_case(
        async_client,
        access_token=tenant["access_token"],
        title="Cross-tenant failure visibility",
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

    await create_invitation(
        async_client,
        access_token=tenant["access_token"],
        email="member@beta.example.com",
        role="member",
    )

    forbidden = await async_client.get(
        "/api/v1/admin/organizations",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert forbidden.status_code == 403

    listed = await async_client.get(
        "/api/v1/admin/organizations",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        params={"search": "beta", "status": "active"},
    )

    assert listed.status_code == 200
    listed_body = listed.json()
    assert len(listed_body) == 1
    organization_row = listed_body[0]
    assert organization_row["slug"] == "beta-claims"
    assert organization_row["open_cases"] == 1
    assert organization_row["active_auth_sessions"] == 1
    assert organization_row["failed_jobs"] >= 1
    assert organization_row["failed_webhook_deliveries"] >= 1
    assert organization_row["failed_emails"] >= 1

    detail = await async_client.get(
        f"/api/v1/admin/organizations/{tenant['organization_id']}",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )

    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["organization"]["slug"] == "beta-claims"
    assert detail_body["total_cases"] == 1
    assert detail_body["members_by_role"]["owner"] == 1
    assert detail_body["jobs_by_status"]["failed"] >= 1
    assert detail_body["webhook_deliveries_by_status"]["failed"] >= 1
    assert detail_body["emails_by_status"]["failed"] >= 1
    assert {item["source"] for item in detail_body["recent_failures"]} == {
        "processing_job",
        "webhook_delivery",
        "outbound_email",
    }


@pytest.mark.asyncio
async def test_platform_admin_can_suspend_and_reactivate_organizations(
    async_client: httpx.AsyncClient,
) -> None:
    admin = await register_owner(
        async_client,
        organization_name="Platform Admins",
        organization_slug="platform-admins",
        email="root@example.com",
    )
    promote_user_to_superuser(email=admin["email"])

    tenant = await register_owner(
        async_client,
        organization_name="Gamma Claims",
        organization_slug="gamma-claims",
        email="owner@gamma.example.com",
    )

    own_suspend = await async_client.post(
        f"/api/v1/admin/organizations/{admin['organization_id']}/suspend",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"reason": "not allowed"},
    )
    assert own_suspend.status_code == 400
    assert own_suspend.json()["error"]["code"] == "current_admin_organization_suspend_forbidden"

    suspended = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/suspend",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"reason": "billing hold"},
    )

    assert suspended.status_code == 200
    suspended_body = suspended.json()
    assert suspended_body["previous_status"] == "active"
    assert suspended_body["current_status"] == "suspended"
    assert suspended_body["revoked_auth_sessions"] == 1
    assert suspended_body["reason"] == "billing hold"

    stale_me = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert stale_me.status_code == 401

    stale_refresh = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tenant["refresh_token"]},
    )
    assert stale_refresh.status_code == 401

    blocked_login = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": tenant["email"],
            "password": "StrongPass123",
            "organization_slug": tenant["organization_slug"],
        },
    )
    assert blocked_login.status_code == 401

    detail_after_suspend = await async_client.get(
        f"/api/v1/admin/organizations/{tenant['organization_id']}",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert detail_after_suspend.status_code == 200
    assert detail_after_suspend.json()["organization"]["status"] == "suspended"
    assert any(
        event["event_type"] == "organization.suspended"
        for event in detail_after_suspend.json()["recent_audit_events"]
    )

    reactivated = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reactivate",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"reason": "billing restored"},
    )

    assert reactivated.status_code == 200
    reactivated_body = reactivated.json()
    assert reactivated_body["previous_status"] == "suspended"
    assert reactivated_body["current_status"] == "active"
    assert reactivated_body["revoked_auth_sessions"] == 0

    stale_me_after_reactivation = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {tenant['access_token']}"},
    )
    assert stale_me_after_reactivation.status_code == 401

    fresh_login = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": tenant["email"],
            "password": "StrongPass123",
            "organization_slug": tenant["organization_slug"],
        },
    )
    assert fresh_login.status_code == 200


@pytest.mark.asyncio
async def test_suspended_organization_invitation_cannot_be_accepted(
    async_client: httpx.AsyncClient,
) -> None:
    admin = await register_owner(
        async_client,
        organization_name="Platform Admins",
        organization_slug="platform-admins",
        email="root@example.com",
    )
    promote_user_to_superuser(email=admin["email"])

    tenant = await register_owner(
        async_client,
        organization_name="Delta Claims",
        organization_slug="delta-claims",
        email="owner@delta.example.com",
    )

    invitation = await create_invitation(
        async_client,
        access_token=tenant["access_token"],
        email="joiner@delta.example.com",
        role="member",
    )

    suspended = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/suspend",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"reason": "manual review"},
    )
    assert suspended.status_code == 200

    accepted = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Case",
        last_name="Joiner",
        password="StrongPass123",
    )
    assert accepted["status_code"] == 400
    assert accepted["body"]["error"]["code"] == "organization_inactive"
