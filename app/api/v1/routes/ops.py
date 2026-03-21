"""Operational endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def healthcheck(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "service": request.app.state.settings.app_name,
        "environment": request.app.state.settings.app_env,
    }


@router.get("/ready", summary="Readiness probe")
async def readiness(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "checks": {
            "application": "ok",
            "database": "pending",
            "redis": "pending",
        },
    }


@router.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
