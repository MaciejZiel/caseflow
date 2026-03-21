from __future__ import annotations

import httpx
import pytest


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


@pytest.mark.asyncio
async def test_register_creates_owner_and_returns_access_token(
    async_client: httpx.AsyncClient,
) -> None:
    response = await async_client.post("/api/v1/auth/register", json=registration_payload())

    body = response.json()
    assert response.status_code == 201
    assert body["access_token"]
    assert body["organization"]["slug"] == "acme-claims"
    assert body["membership"]["role"] == "owner"


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(async_client: httpx.AsyncClient) -> None:
    await async_client.post("/api/v1/auth/register", json=registration_payload())
    response = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(organization_slug="second-org"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_in_use"


@pytest.mark.asyncio
async def test_login_and_me_return_current_session(async_client: httpx.AsyncClient) -> None:
    await async_client.post("/api/v1/auth/register", json=registration_payload())

    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "ada@example.com",
            "password": "StrongPass123",
        },
    )

    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]

    me_response = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "ada@example.com"
