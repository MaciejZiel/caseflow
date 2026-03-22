from __future__ import annotations

from typing import Any
from urllib import error

import pytest

from app.application.services import webhooks as webhook_module
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


@pytest.mark.asyncio
async def test_platform_admin_risk_report_ranks_tenants_by_risk(
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
        },
    ) as async_client:
        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        risky_tenant = await register_owner(
            async_client,
            organization_name="Risky Claims",
            organization_slug="risky-claims",
            email="owner@risky.example.com",
        )
        await register_owner(
            async_client,
            organization_name="Healthy Claims",
            organization_slug="healthy-claims",
            email="owner@healthy.example.com",
        )

        created_endpoint = await async_client.post(
            "/api/v1/webhooks/endpoints",
            headers={"Authorization": f"Bearer {risky_tenant['access_token']}"},
            json={
                "target_url": "https://risky.example.test/webhook",
                "signing_secret": "risky-secret-1234567890",
                "subscribed_event_types": ["case.created"],
            },
        )
        assert created_endpoint.status_code == 201

        risky_case = await create_case(
            async_client,
            access_token=risky_tenant["access_token"],
            title="Risky case",
        )
        risky_document = await async_client.post(
            f"/api/v1/cases/{risky_case['id']}/documents",
            headers={"Authorization": f"Bearer {risky_tenant['access_token']}"},
            json={
                "title": "Broken risky payload",
                "document_type": "attachment",
                "original_filename": "broken.txt",
                "mime_type": "text/plain",
                "content_base64": encode_document_content(b"FAIL_PROCESSING broken payload"),
            },
        )
        assert risky_document.status_code == 201
        await create_invitation(
            async_client,
            access_token=risky_tenant["access_token"],
            email="invite@risky.example.com",
            role="member",
        )

        process_failures = await async_client.post(
            "/api/v1/admin/retry-due",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"limit_per_queue": 20},
        )
        assert process_failures.status_code == 200

        risk_report = await async_client.get(
            "/api/v1/admin/risk-report",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"min_risk_score": 1},
        )
        assert risk_report.status_code == 200

        report_body = risk_report.json()
        assert [item["organization_slug"] for item in report_body] == ["risky-claims"]
        risky_row = report_body[0]
        assert risky_row["risk_score"] == 90
        assert risky_row["risk_level"] == "high"
        assert risky_row["anomaly_count"] == 3
        assert risky_row["critical_anomaly_count"] == 1
        assert risky_row["warning_anomaly_count"] == 2
        assert risky_row["top_anomaly_codes"][0] == "organization_failed_jobs_threshold_exceeded"
        assert set(risky_row["top_anomaly_codes"][1:]) == {
            "organization_failed_webhook_deliveries_threshold_exceeded",
            "organization_failed_emails_threshold_exceeded",
        }

        searched = await async_client.get(
            "/api/v1/admin/risk-report",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"search": "healthy"},
        )
        assert searched.status_code == 200
        assert searched.json()[0]["organization_slug"] == "healthy-claims"
        assert searched.json()[0]["risk_score"] == 0


@pytest.mark.asyncio
async def test_platform_admin_export_returns_csv_operational_snapshot(
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
        },
    ) as async_client:
        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        export_tenant = await register_owner(
            async_client,
            organization_name="Export Claims",
            organization_slug="export-claims",
            email="owner@export.example.com",
        )
        suspended_tenant = await register_owner(
            async_client,
            organization_name="Suspended Claims",
            organization_slug="suspended-claims",
            email="owner@suspended.example.com",
        )

        created_endpoint = await async_client.post(
            "/api/v1/webhooks/endpoints",
            headers={"Authorization": f"Bearer {export_tenant['access_token']}"},
            json={
                "target_url": "https://export.example.test/webhook",
                "signing_secret": "export-secret-1234567890",
                "subscribed_event_types": ["case.created"],
            },
        )
        assert created_endpoint.status_code == 201

        export_case = await create_case(
            async_client,
            access_token=export_tenant["access_token"],
            title="Export case",
        )
        export_document = await async_client.post(
            f"/api/v1/cases/{export_case['id']}/documents",
            headers={"Authorization": f"Bearer {export_tenant['access_token']}"},
            json={
                "title": "Broken export payload",
                "document_type": "attachment",
                "original_filename": "broken.txt",
                "mime_type": "text/plain",
                "content_base64": encode_document_content(b"FAIL_PROCESSING broken payload"),
            },
        )
        assert export_document.status_code == 201
        await create_invitation(
            async_client,
            access_token=export_tenant["access_token"],
            email="invite@export.example.com",
            role="member",
        )

        retry_due = await async_client.post(
            "/api/v1/admin/retry-due",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"limit_per_queue": 20},
        )
        assert retry_due.status_code == 200

        suspended = await async_client.post(
            f"/api/v1/admin/organizations/{suspended_tenant['organization_id']}/suspend",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"reason": "hold"},
        )
        assert suspended.status_code == 200

        exported = await async_client.get(
            "/api/v1/admin/exports/organizations.csv",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"limit": 20},
        )
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        assert (
            exported.headers["content-disposition"]
            == 'attachment; filename="organizations-risk-report.csv"'
        )
        header = exported.text.splitlines()[0]
        assert "organization_slug" in header
        assert "risk_score" in header
        assert "risk_level" in header
        assert "export-claims" in exported.text
        assert "suspended-claims" in exported.text

        active_only = await async_client.get(
            "/api/v1/admin/exports/organizations.csv",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"status": "active", "min_risk_score": 1},
        )
        assert active_only.status_code == 200
        assert "export-claims" in active_only.text
        assert "suspended-claims" not in active_only.text
