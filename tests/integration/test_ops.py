from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_healthcheck_returns_service_metadata(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]


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
