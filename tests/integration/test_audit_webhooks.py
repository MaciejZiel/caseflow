from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib import error

import httpx
import pytest

from app.application.services import webhooks as webhook_module
from app.core.config import get_settings
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
async def test_case_audit_log_and_webhook_delivery_are_recorded(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "caseflow-webhook-secret-123456"
    captured_requests: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        captured_requests.append(
            {
                "data": req.data,
                "headers": dict(req.header_items()),
                "url": req.full_url,
                "timeout": timeout,
            }
        )
        return _FakeWebhookResponse(status=200, body=b'{"ok":true}')

    monkeypatch.setattr(webhook_module.request, "urlopen", fake_urlopen)

    owner = await register_owner(async_client)

    created_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "target_url": "https://example.test/webhook",
            "signing_secret": secret,
        },
    )

    assert created_endpoint.status_code == 201

    listed_endpoints = await async_client.get(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert listed_endpoints.status_code == 200
    assert len(listed_endpoints.json()) == 1

    case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Webhook audited case",
    )

    audit_log = await async_client.get(
        f"/api/v1/cases/{case['id']}/audit-log",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert audit_log.status_code == 200
    assert [item["event_type"] for item in audit_log.json()] == ["case.created"]

    deliveries = await async_client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"event_type": "case.created"},
    )

    assert deliveries.status_code == 200
    assert len(deliveries.json()) == 1
    assert deliveries.json()[0]["status"] == "delivered"
    assert deliveries.json()[0]["http_status"] == 200

    assert len(captured_requests) == 1
    delivered_request = captured_requests[0]
    delivered_body = json.loads(delivered_request["data"].decode("utf-8"))
    delivered_headers = {
        key.lower(): value for key, value in delivered_request["headers"].items()
    }
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        delivered_request["data"],
        hashlib.sha256,
    ).hexdigest()

    assert delivered_body["event_type"] == "case.created"
    assert delivered_body["entity_id"] == case["id"]
    assert delivered_headers["x-caseflow-signature"] == expected_signature


@pytest.mark.asyncio
async def test_document_audit_log_and_failed_webhook_delivery_are_recorded(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    monkeypatch.setattr(webhook_module.request, "urlopen", fake_urlopen)

    owner = await register_owner(async_client)

    created_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "target_url": "https://unreachable.example.test/webhook",
            "signing_secret": "failed-delivery-secret-123456",
        },
    )

    assert created_endpoint.status_code == 201

    case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Document webhook case",
    )
    created_document = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Audited contract",
            "document_type": "contract",
            "original_filename": "audit-contract.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"contract-content"),
        },
    )

    assert created_document.status_code == 201
    document_id = created_document.json()["id"]

    approved_document = await async_client.post(
        f"/api/v1/documents/{document_id}/approve",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"reason": "Everything is valid."},
    )

    assert approved_document.status_code == 200
    assert approved_document.json()["status"] == "approved"

    audit_log = await async_client.get(
        f"/api/v1/documents/{document_id}/audit-log",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert audit_log.status_code == 200
    assert [item["event_type"] for item in audit_log.json()] == [
        "document.uploaded",
        "document.processing_succeeded",
        "document.approved",
    ]

    failed_deliveries = await async_client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"event_type": "document.approved", "status": "failed"},
    )

    assert failed_deliveries.status_code == 200
    assert len(failed_deliveries.json()) == 1
    assert failed_deliveries.json()[0]["status"] == "failed"
    assert failed_deliveries.json()[0]["next_retry_at"] is not None
    assert failed_deliveries.json()[0]["response_body_excerpt"] is not None


@pytest.mark.asyncio
async def test_failed_webhook_delivery_can_be_retried_manually(
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
            "target_url": "https://retry.example.test/webhook",
            "signing_secret": "retry-secret-1234567890",
        },
    )

    assert created_endpoint.status_code == 201

    await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Retryable webhook case",
    )

    failed_deliveries = await async_client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"event_type": "case.created", "status": "failed"},
    )

    assert failed_deliveries.status_code == 200
    assert len(failed_deliveries.json()) == 1
    delivery_id = failed_deliveries.json()[0]["id"]

    should_fail = False
    retried = await async_client.post(
        f"/api/v1/webhooks/deliveries/{delivery_id}/retry",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert retried.status_code == 200
    assert retried.json()["status"] == "delivered"
    assert retried.json()["attempts"] == 2
    assert retried.json()["http_status"] == 200


@pytest.mark.asyncio
async def test_webhook_worker_mode_defers_initial_delivery_until_worker_cycle(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        captured_requests.append(
            {
                "data": req.data,
                "headers": dict(req.header_items()),
                "url": req.full_url,
                "timeout": timeout,
            }
        )
        return _FakeWebhookResponse(status=200, body=b'{"ok":true}')

    monkeypatch.setattr(webhook_module.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("WEBHOOK_DELIVERY_MODE", "worker")
    get_settings.cache_clear()

    owner = await register_owner(async_client)
    created_endpoint = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "target_url": "https://worker-mode.example.test/webhook",
            "signing_secret": "worker-mode-secret-1234567890",
        },
    )

    assert created_endpoint.status_code == 201

    await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Deferred webhook case",
    )

    deliveries_before_worker = await async_client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"event_type": "case.created"},
    )

    assert deliveries_before_worker.status_code == 200
    assert deliveries_before_worker.json()[0]["status"] == "pending"
    assert captured_requests == []

    result = run_retry_cycle(limit_per_queue=10)
    assert result.processed_webhook_deliveries == 1

    deliveries_after_worker = await async_client.get(
        "/api/v1/webhooks/deliveries",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"event_type": "case.created"},
    )

    assert deliveries_after_worker.status_code == 200
    assert deliveries_after_worker.json()[0]["status"] == "delivered"
    assert len(captured_requests) == 1
    get_settings.cache_clear()
