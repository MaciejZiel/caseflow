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
    response = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
        headers={"User-Agent": "CaseFlowBrowser/1.0"},
    )

    body = response.json()
    assert response.status_code == 201
    assert body["access_token"]
    assert body["refresh_token"]
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


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token_and_keeps_session_active(
    async_client: httpx.AsyncClient,
) -> None:
    registration_response = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )
    registration_body = registration_response.json()

    refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": registration_body["refresh_token"]},
    )

    assert refresh_response.status_code == 200
    refresh_body = refresh_response.json()
    assert refresh_body["access_token"] != registration_body["access_token"]
    assert refresh_body["refresh_token"] != registration_body["refresh_token"]

    old_refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": registration_body["refresh_token"]},
    )
    assert old_refresh_response.status_code == 401

    me_response = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {refresh_body['access_token']}"},
    )
    assert me_response.status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_current_session(async_client: httpx.AsyncClient) -> None:
    registration_response = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )
    registration_body = registration_response.json()
    access_token = registration_body["access_token"]
    refresh_token = registration_body["refresh_token"]

    logout_response = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert logout_response.status_code == 204

    me_response = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 401

    refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_all_revokes_other_active_sessions(async_client: httpx.AsyncClient) -> None:
    registration_response = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )
    first_session = registration_response.json()

    second_login_response = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "ada@example.com",
            "password": "StrongPass123",
        },
    )
    second_session = second_login_response.json()

    logout_all_response = await async_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {second_session['access_token']}"},
    )

    assert logout_all_response.status_code == 204

    first_me_response = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {first_session['access_token']}"},
    )
    assert first_me_response.status_code == 401

    second_refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second_session["refresh_token"]},
    )
    assert second_refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_flow_rotates_credentials_and_revokes_sessions(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration_response = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )
    registration_body = registration_response.json()

    reset_token = "password-reset-token-1234567890"
    monkeypatch.setattr("app.application.services.auth.generate_opaque_token", lambda: reset_token)

    request_response = await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "ada@example.com"},
    )
    assert request_response.status_code == 202
    assert request_response.json()["status"] == "accepted"

    confirm_response = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": reset_token,
            "password": "NewStrongPass123",
        },
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["status"] == "password_reset"

    stale_session_response = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {registration_body['access_token']}"},
    )
    assert stale_session_response.status_code == 401

    stale_refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": registration_body["refresh_token"]},
    )
    assert stale_refresh_response.status_code == 401

    old_password_login_response = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "ada@example.com",
            "password": "StrongPass123",
        },
    )
    assert old_password_login_response.status_code == 401

    new_password_login_response = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "ada@example.com",
            "password": "NewStrongPass123",
        },
    )
    assert new_password_login_response.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_confirm_rejects_reused_token(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await async_client.post("/api/v1/auth/register", json=registration_payload())

    reset_token = "reused-reset-token-1234567890"
    monkeypatch.setattr("app.application.services.auth.generate_opaque_token", lambda: reset_token)

    await async_client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "ada@example.com"},
    )

    first_confirm_response = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "password": "NewStrongPass123"},
    )
    second_confirm_response = await async_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "password": "AnotherPass123"},
    )

    assert first_confirm_response.status_code == 200
    assert second_confirm_response.status_code == 400
    assert second_confirm_response.json()["error"]["code"] == "password_reset_token_inactive"


@pytest.mark.asyncio
async def test_auth_sessions_list_shows_current_session_metadata(
    async_client: httpx.AsyncClient,
) -> None:
    registered = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
        headers={"User-Agent": "CaseFlowBrowser/1.0", "X-Forwarded-For": "203.0.113.10"},
    )
    first_session = registered.json()

    second_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "StrongPass123"},
        headers={"User-Agent": "CaseFlowMobile/2.0", "X-Forwarded-For": "198.51.100.25"},
    )
    second_session = second_login.json()

    listed_sessions = await async_client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {second_session['access_token']}"},
    )

    assert listed_sessions.status_code == 200
    sessions = listed_sessions.json()
    assert len(sessions) == 2
    assert sessions[0]["is_current"] is True
    assert sessions[0]["user_agent"] == "CaseFlowMobile/2.0"
    assert sessions[0]["client_ip"] == "198.51.100.25"
    assert sessions[0]["role"] == "owner"
    assert sessions[1]["is_current"] is False
    assert sessions[1]["user_agent"] == "CaseFlowBrowser/1.0"
    assert sessions[1]["client_ip"] == "203.0.113.10"
    assert first_session["refresh_token"] != second_session["refresh_token"]


@pytest.mark.asyncio
async def test_revoke_specific_session_invalidates_only_target_session(
    async_client: httpx.AsyncClient,
) -> None:
    registered = await async_client.post("/api/v1/auth/register", json=registration_payload())
    first_session = registered.json()

    second_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "StrongPass123"},
    )
    second_session = second_login.json()

    listed_sessions = await async_client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {second_session['access_token']}"},
    )
    stale_session_id = next(
        item["id"] for item in listed_sessions.json() if item["is_current"] is False
    )

    revoke_response = await async_client.delete(
        f"/api/v1/auth/sessions/{stale_session_id}",
        headers={"Authorization": f"Bearer {second_session['access_token']}"},
    )
    assert revoke_response.status_code == 204

    stale_me = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {first_session['access_token']}"},
    )
    assert stale_me.status_code == 401

    stale_refresh = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_session["refresh_token"]},
    )
    assert stale_refresh.status_code == 401

    current_me = await async_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {second_session['access_token']}"},
    )
    assert current_me.status_code == 200
