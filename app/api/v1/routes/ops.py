"""Operational endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.infrastructure.db.session import database_is_ready

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def healthcheck(request: Request) -> dict[str, object]:
    return {
        "status": "ok",
        "service": request.app.state.settings.app_name,
        "environment": request.app.state.settings.app_env,
    }


@router.get("/ready", summary="Readiness probe")
async def readiness(request: Request, response: Response) -> dict[str, object]:
    db_ready = database_is_ready()
    if not db_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if db_ready else "degraded",
        "checks": {
            "application": "ok",
            "database": "ok" if db_ready else "error",
            "redis": "pending",
        },
    }


@router.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
