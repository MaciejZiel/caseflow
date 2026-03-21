from __future__ import annotations

import httpx
import pytest

from tests.integration.helpers import accept_invitation, create_invitation, register_owner


@pytest.mark.asyncio
async def test_owner_can_create_and_list_cases(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)

    created = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Insurance claim review",
            "description": "Customer claim for damaged cargo.",
            "external_id": "CASE-001",
            "priority": "high",
        },
    )

    assert created.status_code == 201
    assert created.json()["status"] == "new"

    listed = await async_client.get(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["title"] == "Insurance claim review"


@pytest.mark.asyncio
async def test_case_isolated_between_tenants(async_client: httpx.AsyncClient) -> None:
    owner_one = await register_owner(async_client)
    owner_two_response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other Org",
            "organization_slug": "other-org",
            "first_name": "Second",
            "last_name": "Owner",
            "email": "second-owner@example.com",
            "password": "StrongPass123",
        },
    )
    owner_two_token = owner_two_response.json()["access_token"]

    created = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {owner_one['access_token']}"},
        json={"title": "Tenant one case"},
    )
    case_id = created.json()["id"]

    forbidden_read = await async_client.get(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {owner_two_token}"},
    )

    assert forbidden_read.status_code == 404
    assert forbidden_read.json()["error"]["code"] == "case_not_found"


@pytest.mark.asyncio
async def test_member_can_update_case(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="member@example.com",
        role="member",
    )
    member = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Case",
        last_name="Member",
        password="MemberPass123",
    )

    created = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"title": "Needs update"},
    )
    case_id = created.json()["id"]

    updated = await async_client.patch(
        f"/api/v1/cases/{case_id}",
        headers={"Authorization": f"Bearer {member['body']['access_token']}"},
        json={"status": "in_review", "priority": "urgent"},
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "in_review"
    assert updated.json()["priority"] == "urgent"


@pytest.mark.asyncio
async def test_reviewer_cannot_create_case(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="reviewer@example.com",
        role="reviewer",
    )
    reviewer = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Review",
        last_name="Only",
        password="ReviewerPass123",
    )

    response = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {reviewer['body']['access_token']}"},
        json={"title": "Reviewer should not create"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_case_can_be_archived(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    created = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"title": "Archive me"},
    )
    case_id = created.json()["id"]

    archived = await async_client.post(
        f"/api/v1/cases/{case_id}/archive",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None
