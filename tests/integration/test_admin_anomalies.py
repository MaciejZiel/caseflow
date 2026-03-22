from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.application.services import webhooks as webhook_module
from app.domain.api_keys.models import ApiKeyScope
from app.domain.auth.models import AuthSession
from app.domain.emails.models import OutboundEmail
from app.domain.jobs.models import ProcessingJob
from app.domain.organizations.models import Organization, OrganizationMembership, OrganizationStatus
from app.domain.webhooks.models import WebhookDelivery
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.email.local import LocalEmailSink
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


async def _create_api_key(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": "Ops key", "scopes": [ApiKeyScope.CASES_READ.value]},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_platform_admin_anomalies_surface_ownerless_failed_stale_and_inconsistent_tenants(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def failing_email_deliver(self, email) -> str:
        raise RuntimeError("smtp offline")

    monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
    monkeypatch.setattr(LocalEmailSink, "deliver", failing_email_deliver)

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={
            "DOCUMENT_PROCESSING_MODE": "worker",
            "WEBHOOK_DELIVERY_MODE": "worker",
            "EMAIL_DELIVERY_MODE": "worker",
            "ADMIN_FAILURE_ANOMALY_THRESHOLD": "1",
            "ADMIN_QUEUE_STALE_HOURS": "1",
        },
    ) as async_client:
        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        failing_tenant = await register_owner(
            async_client,
            organization_name="Failing Claims",
            organization_slug="failing-claims",
            email="owner@failing.example.com",
        )
        stale_tenant = await register_owner(
            async_client,
            organization_name="Stale Claims",
            organization_slug="stale-claims",
            email="owner@stale.example.com",
        )
        inconsistent_tenant = await register_owner(
            async_client,
            organization_name="Inconsistent Claims",
            organization_slug="inconsistent-claims",
            email="owner@inconsistent.example.com",
        )
        ownerless_tenant = await register_owner(
            async_client,
            organization_name="Ownerless Claims",
            organization_slug="ownerless-claims",
            email="owner@ownerless.example.com",
        )

        failing_endpoint = await async_client.post(
            "/api/v1/webhooks/endpoints",
            headers={"Authorization": f"Bearer {failing_tenant['access_token']}"},
            json={
                "target_url": "https://failing.example.test/webhook",
                "signing_secret": "failing-secret-1234567890",
                "subscribed_event_types": ["case.created"],
            },
        )
        assert failing_endpoint.status_code == 201

        failing_case = await create_case(
            async_client,
            access_token=failing_tenant["access_token"],
            title="Failing anomaly case",
        )
        failing_document = await async_client.post(
            f"/api/v1/cases/{failing_case['id']}/documents",
            headers={"Authorization": f"Bearer {failing_tenant['access_token']}"},
            json={
                "title": "Broken payload",
                "document_type": "attachment",
                "original_filename": "broken.txt",
                "mime_type": "text/plain",
                "content_base64": encode_document_content(b"FAIL_PROCESSING broken payload"),
            },
        )
        assert failing_document.status_code == 201
        await create_invitation(
            async_client,
            access_token=failing_tenant["access_token"],
            email="invite@failing.example.com",
            role="member",
        )

        retry_failed = await async_client.post(
            "/api/v1/admin/retry-due",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"limit_per_queue": 20},
        )
        assert retry_failed.status_code == 200
        assert retry_failed.json()["processed_document_jobs"] == 1
        assert retry_failed.json()["processed_webhook_deliveries"] == 1
        assert retry_failed.json()["processed_emails"] == 1

        stale_endpoint = await async_client.post(
            "/api/v1/webhooks/endpoints",
            headers={"Authorization": f"Bearer {stale_tenant['access_token']}"},
            json={
                "target_url": "https://stale.example.test/webhook",
                "signing_secret": "stale-secret-1234567890",
                "subscribed_event_types": ["case.created"],
            },
        )
        assert stale_endpoint.status_code == 201

        stale_case = await create_case(
            async_client,
            access_token=stale_tenant["access_token"],
            title="Stale anomaly case",
        )
        stale_document = await async_client.post(
            f"/api/v1/cases/{stale_case['id']}/documents",
            headers={"Authorization": f"Bearer {stale_tenant['access_token']}"},
            json={
                "title": "Queued payload",
                "document_type": "attachment",
                "original_filename": "queued.txt",
                "mime_type": "text/plain",
                "content_base64": encode_document_content(b"queued payload"),
            },
        )
        assert stale_document.status_code == 201
        await create_invitation(
            async_client,
            access_token=stale_tenant["access_token"],
            email="invite@stale.example.com",
            role="member",
        )

        api_key = await _create_api_key(
            async_client,
            access_token=inconsistent_tenant["access_token"],
        )
        assert api_key["plaintext_key"].startswith("cfk_")

        session = get_session_factory()()
        try:
            aged_timestamp = datetime.now(UTC) - timedelta(hours=2)
            ownerless_organization_id = UUID(ownerless_tenant["organization_id"])
            stale_organization_id = UUID(stale_tenant["organization_id"])
            inconsistent_organization_id = UUID(inconsistent_tenant["organization_id"])

            ownerless_membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == ownerless_organization_id
                )
            )
            assert ownerless_membership is not None
            ownerless_membership.is_active = False

            inconsistent_organization = session.get(
                Organization,
                inconsistent_organization_id,
            )
            assert inconsistent_organization is not None
            inconsistent_organization.status = OrganizationStatus.SUSPENDED

            stale_jobs = list(
                session.scalars(
                    select(ProcessingJob).where(
                        ProcessingJob.organization_id == stale_organization_id
                    )
                )
            )
            stale_deliveries = list(
                session.scalars(
                    select(WebhookDelivery).where(
                        WebhookDelivery.organization_id == stale_organization_id
                    )
                )
            )
            stale_emails = list(
                session.scalars(
                    select(OutboundEmail).where(
                        OutboundEmail.organization_id == stale_organization_id
                    )
                )
            )
            inconsistent_sessions = list(
                session.scalars(
                    select(AuthSession).where(
                        AuthSession.organization_id == inconsistent_organization_id
                    )
                )
            )

            assert stale_jobs
            assert stale_deliveries
            assert stale_emails
            assert inconsistent_sessions

            for job in stale_jobs:
                job.scheduled_at = aged_timestamp
                job.next_retry_at = None

            for delivery in stale_deliveries:
                delivery.created_at = aged_timestamp
                delivery.next_retry_at = None

            for email in stale_emails:
                email.scheduled_at = aged_timestamp
                email.next_retry_at = None

            session.commit()
        finally:
            session.close()

        anomalies = await async_client.get(
            "/api/v1/admin/anomalies",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert anomalies.status_code == 200

        anomaly_rows = {
            (item["organization_slug"], item["code"]): item for item in anomalies.json()
        }
        assert (
            "ownerless-claims",
            "organization_without_active_owner",
        ) in anomaly_rows
        assert (
            "failing-claims",
            "organization_failed_jobs_threshold_exceeded",
        ) in anomaly_rows
        assert (
            "failing-claims",
            "organization_failed_webhook_deliveries_threshold_exceeded",
        ) in anomaly_rows
        assert (
            "failing-claims",
            "organization_failed_emails_threshold_exceeded",
        ) in anomaly_rows
        assert (
            "stale-claims",
            "organization_stale_processing_queue",
        ) in anomaly_rows
        assert (
            "stale-claims",
            "organization_stale_webhook_queue",
        ) in anomaly_rows
        assert (
            "stale-claims",
            "organization_stale_email_queue",
        ) in anomaly_rows
        assert (
            "inconsistent-claims",
            "inactive_organization_with_active_api_keys",
        ) in anomaly_rows
        assert (
            "inconsistent-claims",
            "inactive_organization_with_active_auth_sessions",
        ) in anomaly_rows

        critical_only = await async_client.get(
            "/api/v1/admin/anomalies",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"severity": "critical"},
        )
        assert critical_only.status_code == 200
        critical_rows = critical_only.json()
        assert critical_rows
        assert {item["severity"] for item in critical_rows} == {"critical"}
        assert {item["code"] for item in critical_rows} >= {
            "organization_without_active_owner",
            "organization_failed_jobs_threshold_exceeded",
            "inactive_organization_with_active_auth_sessions",
        }
