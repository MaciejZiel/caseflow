from __future__ import annotations

import httpx


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


async def register_owner(async_client: httpx.AsyncClient) -> dict[str, str]:
    response = await async_client.post("/api/v1/auth/register", json=registration_payload())
    body = response.json()
    return {
        "access_token": body["access_token"],
        "organization_slug": body["organization"]["slug"],
        "organization_id": body["organization"]["id"],
    }


async def create_invitation(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    email: str,
    role: str,
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"email": email, "role": role},
    )
    return response.json()


async def accept_invitation(
    async_client: httpx.AsyncClient,
    *,
    token: str,
    first_name: str,
    last_name: str,
    password: str,
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "first_name": first_name,
            "last_name": last_name,
            "password": password,
        },
    )
    return {
        "status_code": response.status_code,
        "body": response.json(),
    }
