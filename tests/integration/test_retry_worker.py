from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.application.services import webhooks as webhook_module
from app.domain.jobs.models import ProcessingJob
from app.domain.webhooks.models import WebhookDelivery
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.storage.local import LocalFileStorage
from app.workers.retries import run_retry_cycle
from tests.integration.helpers import create_case, encode_document_content, register_owner


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
async def test_retry_worker_processes_due_failed_document_job(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])

    created_document = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Retryable processing document",
            "document_type": "other",
            "original_filename": "retryable.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"FAIL_PROCESSING\nbroken payload"),
        },
    )
    assert created_document.status_code == 201
    document_id = created_document.json()["id"]

    versions_response = await async_client.get(
        f"/api/v1/documents/{document_id}/versions",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    jobs_response = await async_client.get(
        f"/api/v1/documents/{document_id}/jobs",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert versions_response.status_code == 200
    assert jobs_response.status_code == 200

    version = versions_response.json()[0]
    failed_job = jobs_response.json()[0]
    assert failed_job["status"] == "failed"
    assert failed_job["next_retry_at"] is not None

    LocalFileStorage().save_file(
        storage_key=version["storage_key"],
        content=b"Recovered payload\nready for extraction\n",
    )

    session = get_session_factory()()
    try:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.id == UUID(failed_job["id"]))
        )
        assert job is not None
        job.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    result = run_retry_cycle(limit_per_queue=10)
    assert result.processed_document_jobs == 1
    assert result.processed_admin_notification_digests == 0

    refreshed_document = await async_client.get(
        f"/api/v1/documents/{document_id}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    refreshed_jobs = await async_client.get(
        f"/api/v1/documents/{document_id}/jobs",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert refreshed_document.status_code == 200
    assert refreshed_document.json()["status"] == "ready"
    assert refreshed_jobs.status_code == 200
    assert refreshed_jobs.json()[0]["status"] == "succeeded"
    assert refreshed_jobs.json()[0]["attempts"] == 2
    assert refreshed_jobs.json()[0]["next_retry_at"] is None


@pytest.mark.asyncio
async def test_retry_worker_processes_due_failed_webhook_delivery(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    should_fail = True

    def fake_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        if should_fail:
            raise error.URLError("connection refused")
        return _FakeWebhookResponse(status=200, body=b'{"ok":true}')

    monkeypatch.setattr(webhook_module.request, "urlopen", fake_urlopen)

    owner = await register_owner(async_client)
    created_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "target_url": "https://retry-worker.example.test/webhook",
            "signing_secret": "retry-worker-secret-1234567890",
        },
    )
    assert created_endpoint.status_code == 201

    await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Retry worker webhook case",
    )

    failed_deliveries = await async_client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"event_type": "case.created", "status": "failed"},
    )
    assert failed_deliveries.status_code == 200
    failed_delivery = failed_deliveries.json()[0]

    session = get_session_factory()()
    try:
        delivery = session.scalar(
            select(WebhookDelivery).where(WebhookDelivery.id == UUID(failed_delivery["id"]))
        )
        assert delivery is not None
        delivery.next_retry_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()

    should_fail = False
    result = run_retry_cycle(limit_per_queue=10)
    assert result.processed_webhook_deliveries == 1
    assert result.processed_admin_notification_digests == 0

    refreshed_deliveries = await async_client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"event_type": "case.created"},
    )
    assert refreshed_deliveries.status_code == 200
    assert refreshed_deliveries.json()[0]["status"] == "delivered"
    assert refreshed_deliveries.json()[0]["attempts"] == 2
    assert refreshed_deliveries.json()[0]["next_retry_at"] is None
