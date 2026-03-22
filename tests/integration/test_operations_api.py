from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error

import httpx
import pytest
from sqlalchemy import select

from app.application.services import webhooks as webhook_module
from app.domain.emails.models import OutboundEmail
from app.domain.webhooks.models import WebhookDelivery
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.email.local import LocalEmailSink
from tests.integration.helpers import (
    configured_async_client,
    create_case,
    create_invitation,
    encode_document_content,
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
async def test_operations_summary_and_failures_surface_recent_problem_items(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def failing_email_deliver(self, email) -> str:
        raise RuntimeError("smtp offline")

    monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
    monkeypatch.setattr(LocalEmailSink, "deliver", failing_email_deliver)

    owner = await register_owner(async_client)
    webhook_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "target_url": "https://ops-failure.example.test/webhook",
            "signing_secret": "ops-failure-secret-1234567890",
            "subscribed_event_types": ["case.created"],
        },
    )
    assert webhook_endpoint.status_code == 201

    case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Operations failure case",
    )
    created_document = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Broken payload",
            "document_type": "attachment",
            "original_filename": "broken.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"FAIL_PROCESSING broken payload"),
        },
    )
    assert created_document.status_code == 201

    await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="ops-failure@example.com",
        role="member",
    )

    summary = await async_client.get(
        "/api/v1/operations/summary",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    failures = await async_client.get(
        "/api/v1/operations/failures",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["webhook_deliveries_by_status"]["failed"] >= 1
    assert summary_body["jobs_by_status"]["failed"] >= 1
    assert summary_body["emails_by_status"]["failed"] >= 1

    assert failures.status_code == 200
    sources = {item["source"] for item in failures.json()}
    assert {"processing_job", "webhook_delivery", "outbound_email"} <= sources


@pytest.mark.asyncio
async def test_operations_retry_due_processes_current_organization_queues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[dict[str, Any]] = []

    def successful_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        captured_requests.append(
            {
                "url": req.full_url,
                "headers": dict(req.header_items()),
                "data": req.data,
            }
        )
        return _FakeWebhookResponse(status=200, body=b'{"ok":true}')

    monkeypatch.setattr(webhook_module.request, "urlopen", successful_urlopen)

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={
            "DOCUMENT_PROCESSING_MODE": "worker",
            "WEBHOOK_DELIVERY_MODE": "worker",
            "EMAIL_DELIVERY_MODE": "worker",
        },
    ) as async_client:
        owner = await register_owner(async_client)
        created_endpoint = await async_client.post(
            "/api/v1/webhooks/endpoints",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
            json={
                "target_url": "https://ops-retry.example.test/webhook",
                "signing_secret": "ops-retry-secret-1234567890",
                "subscribed_event_types": ["case.created"],
            },
        )
        assert created_endpoint.status_code == 201

        case = await create_case(
            async_client,
            access_token=owner["access_token"],
            title="Retry due organization case",
        )
        created_document = await async_client.post(
            f"/api/v1/cases/{case['id']}/documents",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
            json={
                "title": "Queued worker document",
                "document_type": "attachment",
                "original_filename": "queued.txt",
                "mime_type": "text/plain",
                "content_base64": encode_document_content(b"queued worker content"),
            },
        )
        assert created_document.status_code == 201

        await create_invitation(
            async_client,
            access_token=owner["access_token"],
            email="ops-retry@example.com",
            role="member",
        )

        retry_due = await async_client.post(
            "/api/v1/operations/retry-due",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
        )

        assert retry_due.status_code == 200
        retry_body = retry_due.json()
        assert retry_body["processed_document_jobs"] == 1
        assert retry_body["processed_webhook_deliveries"] == 1
        assert retry_body["processed_emails"] == 1

        summary = await async_client.get(
            "/api/v1/operations/summary",
            headers={"Authorization": f"Bearer {owner['access_token']}"},
        )
        assert summary.status_code == 200
        assert summary.json()["jobs_by_status"]["succeeded"] >= 1
        assert summary.json()["webhook_deliveries_by_status"]["delivered"] >= 1
        assert summary.json()["emails_by_status"]["sent"] >= 1
        assert len(captured_requests) == 1


@pytest.mark.asyncio
async def test_operations_retention_preview_and_run_cleanup_old_records(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def successful_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        return _FakeWebhookResponse(status=200, body=b'{"ok":true}')

    monkeypatch.setattr(webhook_module.request, "urlopen", successful_urlopen)

    owner = await register_owner(async_client)
    created_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "target_url": "https://retention.example.test/webhook",
            "signing_secret": "retention-secret-1234567890",
            "subscribed_event_types": ["case.created"],
        },
    )
    assert created_endpoint.status_code == 201

    await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Retention candidate case",
    )
    await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="retention@example.com",
        role="member",
    )

    session = get_session_factory()()
    try:
        aged_timestamp = datetime.now(UTC) - timedelta(days=45)
        webhook_delivery = session.scalar(select(WebhookDelivery))
        outbound_email = session.scalar(select(OutboundEmail))
        assert webhook_delivery is not None
        assert outbound_email is not None
        webhook_delivery.delivered_at = aged_timestamp
        webhook_delivery.created_at = aged_timestamp
        outbound_email.sent_at = aged_timestamp
        outbound_email.created_at = aged_timestamp
        session.commit()
    finally:
        session.close()

    preview = await async_client.get(
        "/api/v1/operations/retention-preview",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert preview.status_code == 200
    assert preview.json()["webhook_deliveries_ready_for_cleanup"] == 1
    assert preview.json()["outbound_emails_ready_for_cleanup"] == 1

    cleanup = await async_client.post(
        "/api/v1/operations/retention-run",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert cleanup.status_code == 200
    assert cleanup.json()["deleted_webhook_deliveries"] == 1
    assert cleanup.json()["deleted_outbound_emails"] == 1

    preview_after = await async_client.get(
        "/api/v1/operations/retention-preview",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert preview_after.status_code == 200
    assert preview_after.json()["webhook_deliveries_ready_for_cleanup"] == 0
    assert preview_after.json()["outbound_emails_ready_for_cleanup"] == 0
