from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.domain.organizations.models import Invitation
from app.infrastructure.db.session import get_session_factory


def registration_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "organization_name": "Acme Claims",
        "organization_slug": "acme-claims",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "password": "StrongPass123",
    }
    payload.update(overrides)
    return payload


async def register_owner(async_client: httpx.AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/register", json=registration_payload())
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_owner_can_create_invitation(async_client: httpx.AsyncClient) -> None:
    access_token = await register_owner(async_client)

    response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"email": "reviewer@example.com", "role": "reviewer"},
    )

    body = response.json()
    assert response.status_code == 201
    assert body["invitation"]["email"] == "reviewer@example.com"
    assert body["invitation"]["role"] == "reviewer"
    assert body["invitation_token"]


@pytest.mark.asyncio
async def test_member_cannot_create_invitation(async_client: httpx.AsyncClient) -> None:
    owner_token = await register_owner(async_client)
    invitation_response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "member@example.com", "role": "member"},
    )

    invitation_token = invitation_response.json()["invitation_token"]
    accepted = await async_client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": invitation_token,
            "first_name": "Grace",
            "last_name": "Hopper",
            "password": "MemberPass123",
        },
    )
    member_token = accepted.json()["access_token"]

    response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"email": "another@example.com", "role": "member"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_accept_invitation_creates_user_and_session(async_client: httpx.AsyncClient) -> None:
    access_token = await register_owner(async_client)
    invitation_response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"email": "reviewer@example.com", "role": "reviewer"},
    )

    accepted = await async_client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": invitation_response.json()["invitation_token"],
            "first_name": "Linus",
            "last_name": "Torvalds",
            "password": "ReviewerPass123",
        },
    )

    assert accepted.status_code == 201
    assert accepted.json()["membership"]["role"] == "reviewer"

    me_response = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {accepted.json()['access_token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "reviewer@example.com"


@pytest.mark.asyncio
async def test_expired_invitation_cannot_be_accepted(async_client: httpx.AsyncClient) -> None:
    access_token = await register_owner(async_client)
    invitation_response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"email": "expired@example.com", "role": "member"},
    )

    session = get_session_factory()()
    try:
        invitation = session.scalar(
            select(Invitation).where(Invitation.email == "expired@example.com")
        )
        assert invitation is not None
        invitation.expires_at = datetime.now(UTC) - timedelta(hours=1)
        session.commit()
    finally:
        session.close()

    accepted = await async_client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": invitation_response.json()["invitation_token"],
            "first_name": "Expired",
            "last_name": "User",
            "password": "ExpiredPass123",
        },
    )

    assert accepted.status_code == 400
    assert accepted.json()["error"]["code"] == "invitation_expired"
