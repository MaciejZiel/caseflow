"""Middleware definitions for HTTP request handling."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.request_context import clear_request_id, set_request_id
from app.infrastructure.observability.metrics import (
    record_http_error,
    record_http_request,
)


def register_http_middleware(app: FastAPI) -> None:
    settings = app.state.settings
    cors_allowed_origins = list(settings.cors_allowed_origins)
    if not cors_allowed_origins and settings.app_env == "local":
        cors_allowed_origins = [
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ]

    if cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    if settings.trusted_host_patterns:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_patterns)

    @app.middleware("http")
    async def add_request_context(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        token = set_request_id(request_id)
        request.state.request_id = request_id

        logger = request.app.state.logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        started_at = perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
        except Exception:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            route = request.scope.get("route")
            route_path = getattr(route, "path", request.url.path)
            record_http_request(
                method=request.method,
                path=route_path,
                status_code=500,
                duration_seconds=duration_ms / 1000,
            )
            record_http_error(method=request.method, path=route_path, status_code=500)
            logger.exception("request_failed", duration_ms=duration_ms)
            clear_request_id(token)
            raise

        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        record_http_request(
            method=request.method,
            path=route_path,
            status_code=response.status_code,
            duration_seconds=duration_ms / 1000,
        )
        if response.status_code >= 500:
            record_http_error(
                method=request.method,
                path=route_path,
                status_code=response.status_code,
            )

        response.headers["X-Request-ID"] = request_id
        if settings.security_headers_enabled:
            _set_default_security_headers(
                response,
                request=request,
                hsts_max_age_seconds=settings.security_hsts_max_age_seconds,
            )
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        clear_request_id(token)
        return response


def _set_default_security_headers(
    response: Response,
    *,
    request: Request,
    hsts_max_age_seconds: int,
) -> None:
    default_headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    for header_name, header_value in default_headers.items():
        if header_name not in response.headers:
            response.headers[header_name] = header_value

    if request.url.scheme == "https" and hsts_max_age_seconds > 0:
        response.headers["Strict-Transport-Security"] = (
            f"max-age={hsts_max_age_seconds}; includeSubDomains"
        )
