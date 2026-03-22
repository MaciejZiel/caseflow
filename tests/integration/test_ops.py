from __future__ import annotations

import httpx
import pytest

from tests.integration.helpers import configured_async_client


@pytest.mark.asyncio
async def test_healthcheck_returns_service_metadata(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


@pytest.mark.asyncio
async def test_readiness_returns_database_status(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_metrics_exposes_prometheus_payload(async_client: httpx.AsyncClient) -> None:
    await async_client.get("/health")
    response = await async_client.get("/metrics")

    assert response.status_code == 200
    assert "caseflow_http_requests_total" in response.text


@pytest.mark.asyncio
async def test_not_found_uses_standard_error_shape(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_cors_preflight_allows_configured_origin(tmp_path, monkeypatch) -> None:
    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"CORS_ALLOWED_ORIGINS": "[\"https://app.caseflow.test\"]"},
    ) as async_client:
        response = await async_client.options(
            "/health",
            headers={
                "Origin": "https://app.caseflow.test",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.caseflow.test"
    assert "GET" in response.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_trusted_host_middleware_blocks_unconfigured_hosts(tmp_path, monkeypatch) -> None:
    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"TRUSTED_HOST_PATTERNS": "[\"testserver\", \"api.caseflow.test\"]"},
    ) as async_client:
        response = await async_client.get("/health", headers={"Host": "evil.caseflow.test"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_forwarded_for_is_ignored_when_proxy_trust_is_disabled(
    tmp_path,
    monkeypatch,
) -> None:
    async with configured_async_client(
        tmp_path,
        monkeypatch,
        env_overrides={"TRUST_PROXY_HEADERS": "false"},
    ) as async_client:
        registered = await async_client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": "Proxy Safe Org",
                "organization_slug": "proxy-safe-org",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "proxy-safe@example.com",
                "password": "StrongPass123",
            },
            headers={
                "User-Agent": "CaseFlowBrowser/1.0",
                "X-Forwarded-For": "198.51.100.77",
            },
        )
        access_token = registered.json()["access_token"]

        sessions = await async_client.get(
            "/api/v1/auth/sessions",
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "CaseFlowBrowser/1.0",
                "X-Forwarded-For": "198.51.100.77",
            },
        )

    assert sessions.status_code == 200
    current_session = sessions.json()[0]
    assert current_session["client_ip"] != "198.51.100.77"
    assert current_session["last_seen_ip"] != "198.51.100.77"
