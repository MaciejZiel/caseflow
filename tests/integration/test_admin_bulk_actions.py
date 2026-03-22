from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from tests.integration.helpers import promote_user_to_superuser, register_owner


@pytest.mark.asyncio
async def test_platform_admin_can_bulk_suspend_and_reactivate_organizations(
    async_client: httpx.AsyncClient,
) -> None:
    admin = await register_owner(
        async_client,
        organization_name="Platform Admins",
        organization_slug="platform-admins",
        email="root@example.com",
    )
    promote_user_to_superuser(email=admin["email"])

    tenant_one = await register_owner(
        async_client,
        organization_name="Bulk Alpha",
        organization_slug="bulk-alpha",
        email="owner@bulk-alpha.example.com",
    )
    tenant_two = await register_owner(
        async_client,
        organization_name="Bulk Beta",
        organization_slug="bulk-beta",
        email="owner@bulk-beta.example.com",
    )

    bulk_suspend = await async_client.post(
        "/api/v1/admin/organizations/bulk-status",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "organization_ids": [
                tenant_one["organization_id"],
                tenant_two["organization_id"],
                admin["organization_id"],
            ],
            "action": "suspend",
            "reason": "incident response",
        },
    )

    assert bulk_suspend.status_code == 200
    suspend_body = bulk_suspend.json()
    assert suspend_body["action"] == "suspend"
    assert suspend_body["total_requested"] == 3
    assert suspend_body["updated_count"] == 2
    assert suspend_body["failed_count"] == 1

    failed_items = [item for item in suspend_body["results"] if item["outcome"] == "failed"]
    assert len(failed_items) == 1
    assert failed_items[0]["organization_id"] == admin["organization_id"]
    assert failed_items[0]["error_code"] == "current_admin_organization_suspend_forbidden"

    updated_items = [item for item in suspend_body["results"] if item["outcome"] == "updated"]
    assert {item["organization_slug"] for item in updated_items} == {"bulk-alpha", "bulk-beta"}
    assert all(item["current_status"] == "suspended" for item in updated_items)
    assert all(item["revoked_auth_sessions"] == 1 for item in updated_items)

    stale_me_tenant_one = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {tenant_one['access_token']}"},
    )
    stale_me_tenant_two = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {tenant_two['access_token']}"},
    )
    assert stale_me_tenant_one.status_code == 401
    assert stale_me_tenant_two.status_code == 401

    bulk_reactivate = await async_client.post(
        "/api/v1/admin/organizations/bulk-status",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "organization_ids": [tenant_one["organization_id"], tenant_two["organization_id"]],
            "action": "reactivate",
            "reason": "incident resolved",
        },
    )

    assert bulk_reactivate.status_code == 200
    reactivate_body = bulk_reactivate.json()
    assert reactivate_body["action"] == "reactivate"
    assert reactivate_body["updated_count"] == 2
    assert reactivate_body["failed_count"] == 0
    assert all(item["current_status"] == "active" for item in reactivate_body["results"])

    tenant_one_login = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": tenant_one["email"],
            "password": "StrongPass123",
            "organization_slug": tenant_one["organization_slug"],
        },
    )
    tenant_two_login = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": tenant_two["email"],
            "password": "StrongPass123",
            "organization_slug": tenant_two["organization_slug"],
        },
    )
    assert tenant_one_login.status_code == 200
    assert tenant_two_login.status_code == 200


@pytest.mark.asyncio
async def test_bulk_status_rejects_duplicate_ids_and_invalid_action(
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
        organization_name="Bulk Validation",
        organization_slug="bulk-validation",
        email="owner@bulk-validation.example.com",
    )

    duplicate_ids = [tenant["organization_id"], tenant["organization_id"]]
    assert len({UUID(value) for value in duplicate_ids}) == 1

    invalid_action = await async_client.post(
        "/api/v1/admin/organizations/bulk-status",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "organization_ids": duplicate_ids,
            "action": "pause",
        },
    )
    assert invalid_action.status_code == 422

    valid_request = await async_client.post(
        "/api/v1/admin/organizations/bulk-status",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={
            "organization_ids": duplicate_ids,
            "action": "suspend",
        },
    )
    assert valid_request.status_code == 200
    assert valid_request.json()["total_requested"] == 1
