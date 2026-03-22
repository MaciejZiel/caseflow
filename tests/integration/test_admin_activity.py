from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.integration.helpers import (
    configured_async_client,
    create_case,
    encode_document_content,
    promote_user_to_superuser,
    register_owner,
)


@pytest.mark.asyncio
async def test_platform_admin_can_inspect_filtered_tenant_activity_feed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"DOCUMENT_PROCESSING_MODE": "worker"},
    ) as async_client:
        admin = await register_owner(
            async_client,
            organization_name="Platform Admins",
            organization_slug="platform-admins",
            email="root@example.com",
        )
        promote_user_to_superuser(email=admin["email"])

        tenant = await register_owner(
            async_client,
            organization_name="Activity Claims",
            organization_slug="activity-claims",
            email="owner@activity.example.com",
        )

        created_case = await create_case(
            async_client,
            access_token=tenant["access_token"],
            title="Activity feed case",
        )

        created_comment = await async_client.post(
            f"/api/v1/cases/{created_case['id']}/comments",
            headers={"Authorization": f"Bearer {tenant['access_token']}"},
            json={"body": "Need one more attachment before approval."},
        )
        assert created_comment.status_code == 201

        updated_case = await async_client.patch(
            f"/api/v1/cases/{created_case['id']}",
            headers={"Authorization": f"Bearer {tenant['access_token']}"},
            json={"status": "in_review", "priority": "urgent"},
        )
        assert updated_case.status_code == 200

        created_document = await async_client.post(
            f"/api/v1/cases/{created_case['id']}/documents",
            headers={"Authorization": f"Bearer {tenant['access_token']}"},
            json={
                "title": "Activity attachment",
                "document_type": "attachment",
                "original_filename": "activity.txt",
                "mime_type": "text/plain",
                "content_base64": encode_document_content(b"activity payload"),
            },
        )
        assert created_document.status_code == 201

        activity = await async_client.get(
            f"/api/v1/admin/organizations/{tenant['organization_id']}/activity",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
        )
        assert activity.status_code == 200

        activity_body = activity.json()
        assert [item["created_at"] for item in activity_body] == sorted(
            (item["created_at"] for item in activity_body),
            reverse=True,
        )
        assert {item["event_type"] for item in activity_body} >= {
            "case.created",
            "case.comment_created",
            "case.updated",
            "case.status_changed",
            "document.uploaded",
        }
        assert activity_body[-1]["event_type"] == "case.created"

        comment_events = await async_client.get(
            f"/api/v1/admin/organizations/{tenant['organization_id']}/activity",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"event_type": "case.comment_created"},
        )
        assert comment_events.status_code == 200
        assert len(comment_events.json()) == 1
        assert comment_events.json()[0]["metadata_json"]["body_excerpt"].startswith("Need one more")

        document_events = await async_client.get(
            f"/api/v1/admin/organizations/{tenant['organization_id']}/activity",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"entity_type": "document"},
        )
        assert document_events.status_code == 200
        assert {item["entity_type"] for item in document_events.json()} == {"document"}
        assert document_events.json()[0]["event_type"] == "document.uploaded"

        actor_filtered = await async_client.get(
            f"/api/v1/admin/organizations/{tenant['organization_id']}/activity",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"actor_user_id": tenant["user_id"]},
        )
        assert actor_filtered.status_code == 200
        assert actor_filtered.json()
        assert {item["actor_user_id"] for item in actor_filtered.json()} == {tenant["user_id"]}

        since_future = await async_client.get(
            f"/api/v1/admin/organizations/{tenant['organization_id']}/activity",
            headers={"Authorization": f"Bearer {admin['access_token']}"},
            params={"since": datetime(2099, 1, 1, tzinfo=UTC).isoformat()},
        )
        assert since_future.status_code == 200
        assert since_future.json() == []
