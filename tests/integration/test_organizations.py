from __future__ import annotations

import httpx
import pytest

from tests.integration.helpers import accept_invitation, create_invitation, register_owner


@pytest.mark.asyncio
async def test_current_organization_returns_actor_context(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)

    response = await async_client.get(
        "/api/v1/organizations/current",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["organization"]["slug"] == owner["organization_slug"]
    assert response.json()["membership"]["role"] == "owner"


@pytest.mark.asyncio
async def test_owner_can_list_members(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="reviewer@example.com",
        role="reviewer",
    )
    await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Review",
        last_name="User",
        password="ReviewerPass123",
    )

    response = await async_client.get(
        "/api/v1/organizations/current/members",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert {member["user"]["email"] for member in response.json()} == {
        "ada@example.com",
        "reviewer@example.com",
    }


@pytest.mark.asyncio
async def test_member_cannot_list_members(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="member@example.com",
        role="member",
    )
    accepted = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Member",
        last_name="User",
        password="MemberPass123",
    )

    response = await async_client.get(
        "/api/v1/organizations/current/members",
        headers={"Authorization": f"Bearer {accepted['body']['access_token']}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_owner_can_update_member_role_and_activity(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="member@example.com",
        role="member",
    )
    accepted = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Member",
        last_name="User",
        password="MemberPass123",
    )
    membership_id = accepted["body"]["membership"]["id"]

    response = await async_client.patch(
        f"/api/v1/organizations/current/members/{membership_id}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"role": "reviewer", "is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "reviewer"
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_admin_cannot_assign_owner_role(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)

    admin_invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="admin@example.com",
        role="admin",
    )
    admin = await accept_invitation(
        async_client,
        token=str(admin_invitation["invitation_token"]),
        first_name="Admin",
        last_name="User",
        password="AdminPass123",
    )

    member_invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="member@example.com",
        role="member",
    )
    member = await accept_invitation(
        async_client,
        token=str(member_invitation["invitation_token"]),
        first_name="Normal",
        last_name="Member",
        password="MemberPass123",
    )
    membership_id = member["body"]["membership"]["id"]

    response = await async_client.patch(
        f"/api/v1/organizations/current/members/{membership_id}",
        headers={"Authorization": f"Bearer {admin['body']['access_token']}"},
        json={"role": "owner"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "owner_assignment_forbidden"
