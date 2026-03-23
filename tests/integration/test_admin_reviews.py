from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error

import httpx
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

    created_invitation = await create_invitation(
        async_client,
        access_token=tenant["access_token"],
        email=f"member@{organization_slug}.example.com",
        role="member",
    )
    assert created_invitation["invitation"]["id"] is not None
    return tenant


@pytest.mark.asyncio
async def test_platform_admin_review_queue_captures_risk_snapshots_and_comments(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def failing_email_deliver(self, email) -> str:
        raise RuntimeError("smtp offline")

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"ADMIN_FAILURE_ANOMALY_THRESHOLD": "1"},
    ) as async_client:
        monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
        monkeypatch.setattr(LocalEmailSink, "deliver", failing_email_deliver)

        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        tenant = await _create_risky_tenant(
            async_client,
            organization_name="Review Target",
            organization_slug="review-target",
            email="owner@review-target.example.com",
        )

        created_review = await async_client.post(
            f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={
                "title": "Investigate tenant failures",
                "summary": "Cross-queue failures should be triaged immediately.",
                "assigned_to_user_id": admin["user_id"],
                "due_at": "2030-01-15T12:00:00Z",
            },
        )

        assert created_review.status_code == 201
        created_body = created_review.json()
        assert created_body["organization"]["slug"] == "review-target"
        assert created_body["priority"] == "high"
        assert created_body["risk_score_snapshot"] == 90
        assert created_body["risk_level_snapshot"] == "high"
        assert created_body["anomaly_count_snapshot"] == 3
        assert (
            created_body["top_anomaly_codes_snapshot"][0]
            == "organization_failed_jobs_threshold_exceeded"
        )
        assert set(created_body["top_anomaly_codes_snapshot"][1:]) == {
            "organization_failed_webhook_deliveries_threshold_exceeded",
            "organization_failed_emails_threshold_exceeded",
        }
        assert created_body["assigned_to"]["email"] == admin["email"]
        assert created_body["comment_count"] == 0

        summary = await async_client.get(
            "/api/v1/admin/reviews/summary",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert summary.status_code == 200
        summary_body = summary.json()
        assert summary_body["total_reviews"] == 1
        assert summary_body["active_review_count"] == 1
        assert summary_body["counts_by_status"]["open"] == 1
        assert summary_body["counts_by_priority"]["high"] == 1

        comment = await async_client.post(
            f"/api/v1/admin/reviews/{created_body['id']}/comments",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"body": "Queued for manual platform investigation."},
        )
        assert comment.status_code == 201

        updated_review = await async_client.patch(
            f"/api/v1/admin/reviews/{created_body['id']}",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"status": "in_progress"},
        )
        assert updated_review.status_code == 200
        assert updated_review.json()["status"] == "in_progress"

        listed_reviews = await async_client.get(
            "/api/v1/admin/reviews",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"assigned_to_me": "true", "status": "in_progress"},
        )
        assert listed_reviews.status_code == 200
        assert [item["id"] for item in listed_reviews.json()] == [created_body["id"]]

        detail = await async_client.get(
            f"/api/v1/admin/reviews/{created_body['id']}",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["status"] == "in_progress"
        assert detail_body["comment_count"] == 1
        assert detail_body["comments"][0]["author"]["email"] == admin["email"]
        assert detail_body["comments"][0]["body"] == "Queued for manual platform investigation."

        tenant_detail = await async_client.get(
            f"/api/v1/admin/organizations/{tenant['organization_id']}",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert tenant_detail.status_code == 200
        event_types = {
            item["event_type"] for item in tenant_detail.json()["recent_audit_events"]
        }
        assert {
            "admin_review.created",
            "admin_review.updated",
            "admin_review.comment_added",
        } <= event_types


@pytest.mark.asyncio
async def test_platform_admin_review_workload_and_attention_queue(
    async_client: httpx.AsyncClient,
) -> None:
    admin = await register_owner(
        async_client,
        organization_name="Platform Admins",
        organization_slug="platform-admins",
        email="root@example.com",
    )
    promote_user_to_superuser(email=admin["email"])

    second_admin = await register_owner(
        async_client,
        organization_name="Platform Ops",
        organization_slug="platform-ops",
        email="ops@example.com",
    )
    promote_user_to_superuser(email=second_admin["email"])

    now = datetime.now(UTC)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_tomorrow = start_of_today + timedelta(days=1)
    due_today = min(now + timedelta(hours=1), start_of_tomorrow - timedelta(minutes=1))
    due_soon = start_of_today + timedelta(days=2, hours=9)
    overdue = now - timedelta(days=2, hours=3)

    overdue_tenant = await register_owner(
        async_client,
        organization_name="Overdue Tenant",
        organization_slug="overdue-tenant",
        email="owner@overdue-tenant.example.com",
    )
    due_today_tenant = await register_owner(
        async_client,
        organization_name="Due Today Tenant",
        organization_slug="due-today-tenant",
        email="owner@due-today-tenant.example.com",
    )
    unassigned_tenant = await register_owner(
        async_client,
        organization_name="Unassigned Tenant",
        organization_slug="unassigned-tenant",
        email="owner@unassigned-tenant.example.com",
    )

    overdue_review = await async_client.post(
        f"/api/v1/admin/organizations/{overdue_tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "title": "Overdue urgent review",
            "priority": "urgent",
            "assigned_to_user_id": second_admin["user_id"],
            "due_at": overdue.isoformat(),
        },
    )
    assert overdue_review.status_code == 201

    due_today_review = await async_client.post(
        f"/api/v1/admin/organizations/{due_today_tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "title": "Due today review",
            "assigned_to_user_id": admin["user_id"],
            "due_at": due_today.isoformat(),
        },
    )
    assert due_today_review.status_code == 201

    due_soon_review = await async_client.post(
        f"/api/v1/admin/organizations/{unassigned_tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "title": "Unassigned due soon review",
            "due_at": due_soon.isoformat(),
        },
    )
    assert due_soon_review.status_code == 201

    workload = await async_client.get(
        "/api/v1/admin/reviews/workload",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        params={"limit": 10},
    )
    assert workload.status_code == 200
    workload_body = workload.json()
    assert [item["assignee"]["email"] if item["assignee"] else None for item in workload_body] == [
        second_admin["email"],
        admin["email"],
        None,
    ]
    assert workload_body[0]["overdue_review_count"] == 1
    assert workload_body[0]["urgent_review_count"] == 1
    assert workload_body[0]["top_review_id"] == overdue_review.json()["id"]
    assert workload_body[1]["due_today_count"] == 1
    assert workload_body[1]["top_review_id"] == due_today_review.json()["id"]
    assert workload_body[2]["due_soon_count"] == 1
    assert workload_body[2]["assignee"] is None
    assert workload_body[2]["top_review_id"] == due_soon_review.json()["id"]

    attention_queue = await async_client.get(
        "/api/v1/admin/reviews/attention-queue",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        params={"limit": 10},
    )
    assert attention_queue.status_code == 200
    attention_body = attention_queue.json()
    assert [item["id"] for item in attention_body] == [
        overdue_review.json()["id"],
        due_today_review.json()["id"],
        due_soon_review.json()["id"],
    ]
    assert attention_body[0]["attention_reasons"][:2] == ["overdue", "urgent"]
    assert attention_body[0]["days_overdue"] >= 2
    assert attention_body[1]["attention_reasons"] == ["due_today"]
    assert attention_body[2]["attention_reasons"] == ["due_soon", "unassigned"]


@pytest.mark.asyncio
async def test_platform_admin_can_preview_and_auto_open_reviews_from_risk_report(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_urlopen(req: Any, timeout: int = 0) -> _FakeWebhookResponse:
        raise error.URLError("connection refused")

    def failing_email_deliver(self, email) -> str:
        raise RuntimeError("smtp offline")

    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"ADMIN_FAILURE_ANOMALY_THRESHOLD": "1"},
    ) as async_client:
        monkeypatch.setattr(webhook_module.request, "urlopen", failing_urlopen)
        monkeypatch.setattr(LocalEmailSink, "deliver", failing_email_deliver)

        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        auto_open_target = await _create_risky_tenant(
            async_client,
            organization_name="Auto Open Target",
            organization_slug="auto-open-target",
            email="owner@auto-open-target.example.com",
        )
        existing_review_target = await _create_risky_tenant(
            async_client,
            organization_name="Existing Review Target",
            organization_slug="existing-review-target",
            email="owner@existing-review-target.example.com",
        )

        created_manual_review = await async_client.post(
            f"/api/v1/admin/organizations/{existing_review_target['organization_id']}/reviews",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={"title": "Existing manual review"},
        )
        assert created_manual_review.status_code == 201

        preview = await async_client.get(
            "/api/v1/admin/reviews/auto-open-preview",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"min_risk_score": 50, "limit": 10},
        )
        assert preview.status_code == 200
        preview_rows = {
            item["organization"]["slug"]: item
            for item in preview.json()
        }
        assert preview_rows["auto-open-target"]["has_active_review"] is False
        assert preview_rows["existing-review-target"]["has_active_review"] is True
        assert preview_rows["auto-open-target"]["suggested_priority"] == "high"

        auto_open = await async_client.post(
            "/api/v1/admin/reviews/auto-open",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            json={
                "min_risk_score": 50,
                "limit": 10,
                "assigned_to_user_id": admin["user_id"],
                "due_in_days": 2,
            },
        )
        assert auto_open.status_code == 200
        auto_open_body = auto_open.json()
        assert auto_open_body["created_count"] == 1
        assert auto_open_body["skipped_count"] == 1

        result_by_slug = {
            item["organization"]["slug"]: item
            for item in auto_open_body["results"]
        }
        assert result_by_slug["auto-open-target"]["outcome"] == "created"
        assert result_by_slug["existing-review-target"]["outcome"] == "skipped"
        assert result_by_slug["existing-review-target"]["reason"] == "active_review_exists"

        created_review_detail = await async_client.get(
            f"/api/v1/admin/reviews/{result_by_slug['auto-open-target']['review_id']}",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert created_review_detail.status_code == 200
        created_review_body = created_review_detail.json()
        assert created_review_body["organization"]["id"] == auto_open_target["organization_id"]
        assert created_review_body["assigned_to"]["email"] == admin["email"]
        assert created_review_body["priority"] == "high"
        assert created_review_body["due_at"] is not None
        assert created_review_body["title"] == (
            "Platform review: Auto Open Target (high risk)"
        )


@pytest.mark.asyncio
async def test_platform_admin_can_preview_and_escalate_overdue_reviews(
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
        organization_name="Overdue Review Tenant",
        organization_slug="overdue-review-tenant",
        email="owner@overdue-review.example.com",
    )

    created_review = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "title": "Overdue platform review",
            "due_at": "2024-01-10T09:00:00Z",
        },
    )
    assert created_review.status_code == 201
    created_body = created_review.json()
    assert created_body["priority"] == "low"

    preview = await async_client.get(
        "/api/v1/admin/reviews/escalation-preview",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        params={"min_days_overdue": 1, "limit": 10},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert len(preview_body) == 1
    assert preview_body[0]["review_id"] == created_body["id"]
    assert preview_body[0]["needs_priority_bump"] is True
    assert preview_body[0]["is_unassigned"] is True
    assert preview_body[0]["days_overdue"] >= 1

    escalated = await async_client.post(
        "/api/v1/admin/reviews/escalate-overdue",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "min_days_overdue": 1,
            "limit": 10,
            "assigned_to_user_id": admin["user_id"],
        },
    )
    assert escalated.status_code == 200
    escalated_body = escalated.json()
    assert escalated_body["escalated_count"] == 1
    assert escalated_body["skipped_count"] == 0
    assert escalated_body["results"][0]["outcome"] == "escalated"
    assert escalated_body["results"][0]["previous_priority"] == "low"
    assert escalated_body["results"][0]["current_priority"] == "urgent"
    assert escalated_body["results"][0]["added_comment"] is True

    detail = await async_client.get(
        f"/api/v1/admin/reviews/{created_body['id']}",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["priority"] == "urgent"
    assert detail_body["assigned_to"]["email"] == admin["email"]
    assert detail_body["comment_count"] == 1
    assert "overdue" in detail_body["comments"][0]["body"].lower()


@pytest.mark.asyncio
async def test_overdue_escalation_skips_reviews_that_are_already_escalated(
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
        organization_name="Already Escalated Tenant",
        organization_slug="already-escalated-tenant",
        email="owner@already-escalated.example.com",
    )

    created_review = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "title": "Already urgent review",
            "priority": "urgent",
            "assigned_to_user_id": admin["user_id"],
            "due_at": "2024-01-10T09:00:00Z",
        },
    )
    assert created_review.status_code == 201

    escalated = await async_client.post(
        "/api/v1/admin/reviews/escalate-overdue",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "min_days_overdue": 1,
            "limit": 10,
            "assigned_to_user_id": admin["user_id"],
        },
    )
    assert escalated.status_code == 200
    escalated_body = escalated.json()
    assert escalated_body["escalated_count"] == 0
    assert escalated_body["skipped_count"] == 1
    assert escalated_body["results"][0]["outcome"] == "skipped"
    assert escalated_body["results"][0]["reason"] == "already_escalated"


@pytest.mark.asyncio
async def test_platform_admin_review_queue_enforces_assignee_rules_and_active_uniqueness(
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
        organization_name="Escalation Tenant",
        organization_slug="escalation-tenant",
        email="owner@escalation.example.com",
    )

    invalid_assignee = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "title": "Invalid assignee test",
            "assigned_to_user_id": tenant["user_id"],
        },
    )
    assert invalid_assignee.status_code == 400
    assert invalid_assignee.json()["error"]["code"] == "admin_review_assignee_invalid"

    created_review = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"title": "Primary platform review"},
    )
    assert created_review.status_code == 201
    created_body = created_review.json()
    assert created_body["status"] == "open"

    duplicate_review = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"title": "Duplicate platform review"},
    )
    assert duplicate_review.status_code == 400
    assert duplicate_review.json()["error"]["code"] == "organization_review_already_open"

    resolved_review = await async_client.patch(
        f"/api/v1/admin/reviews/{created_body['id']}",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"status": "resolved", "assigned_to_user_id": None},
    )
    assert resolved_review.status_code == 200
    resolved_body = resolved_review.json()
    assert resolved_body["status"] == "resolved"
    assert resolved_body["resolved_at"] is not None
    assert resolved_body["assigned_to"] is None

    reopened_queue = await async_client.post(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"title": "Follow-up platform review", "priority": "urgent"},
    )
    assert reopened_queue.status_code == 201

    organization_reviews = await async_client.get(
        f"/api/v1/admin/organizations/{tenant['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert organization_reviews.status_code == 200
    organization_review_statuses = [item["status"] for item in organization_reviews.json()]
    assert organization_review_statuses == ["open", "resolved"]


@pytest.mark.asyncio
async def test_non_superuser_cannot_access_platform_review_queue(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(
        async_client,
        organization_name="Tenant Alpha",
        organization_slug="tenant-alpha",
        email="owner@tenant-alpha.example.com",
    )

    forbidden_list = await async_client.get(
        "/api/v1/admin/reviews",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert forbidden_list.status_code == 403

    forbidden_create = await async_client.post(
        f"/api/v1/admin/organizations/{owner['organization_id']}/reviews",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"title": "Should be forbidden"},
    )
    assert forbidden_create.status_code == 403
