import httpx
import pytest

from app.main import create_app


@pytest.mark.asyncio
async def test_healthcheck_returns_service_metadata() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_readiness_returns_placeholder_dependency_status() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "pending"


@pytest.mark.asyncio
async def test_metrics_exposes_prometheus_payload() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.get("/health")
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "caseflow_http_requests_total" in response.text


@pytest.mark.asyncio
async def test_not_found_uses_standard_error_shape() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
