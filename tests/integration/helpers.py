from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence

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


async def create_case(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    title: str = "Primary case",
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"title": title},
    )
    return response.json()


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


def encode_document_content(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


async def wait_for_document_status(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    document_id: str,
    expected_statuses: Sequence[str],
    attempts: int = 5,
) -> dict[str, object]:
    response_body: dict[str, object] = {}
    for _ in range(attempts):
        response = await async_client.get(
            f"/api/v1/documents/{document_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response_body = response.json()
        if response_body["status"] in expected_statuses:
            return response_body
        await asyncio.sleep(0.02)
    return response_body
