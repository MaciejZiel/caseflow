from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.domain.organizations.models import Invitation
from app.infrastructure.db.session import get_session_factory
from tests.integration.helpers import accept_invitation, create_invitation, register_owner


@pytest.mark.asyncio
async def test_owner_can_create_invitation(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    body = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="reviewer@example.com",
        role="reviewer",
    )

    assert body["invitation"]["email"] == "reviewer@example.com"
    assert body["invitation"]["role"] == "reviewer"
    assert body["invitation_token"]


@pytest.mark.asyncio
async def test_member_cannot_create_invitation(async_client: httpx.AsyncClient) -> None:
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
        first_name="Grace",
        last_name="Hopper",
        password="MemberPass123",
    )
    member_token = accepted["body"]["access_token"]

    response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email": "another@example.com", "role": "member"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_accept_invitation_creates_user_and_session(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="reviewer@example.com",
        role="reviewer",
    )
    accepted = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Linus",
        last_name="Torvalds",
        password="ReviewerPass123",
    )

    assert accepted["status_code"] == 201
    assert accepted["body"]["membership"]["role"] == "reviewer"

    me_response = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {accepted['body']['access_token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "reviewer@example.com"


@pytest.mark.asyncio
async def test_expired_invitation_cannot_be_accepted(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="expired@example.com",
        role="member",
    )

    session = get_session_factory()()
    try:
        invitation_record = session.scalar(
            select(Invitation).where(Invitation.email == "expired@example.com")
        )
        assert invitation_record is not None
        invitation_record.expires_at = datetime.now(UTC) - timedelta(hours=1)
        session.commit()
    finally:
        session.close()

    accepted = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Expired",
        last_name="User",
        password="ExpiredPass123",
    )

    assert accepted["status_code"] == 400
    assert accepted["body"]["error"]["code"] == "invitation_expired"
