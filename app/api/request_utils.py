"""Helpers for request metadata extraction."""

from __future__ import annotations

from fastapi import Request

from app.core.config import get_settings


def extract_client_ip(request: Request) -> str | None:
    settings = getattr(request.app.state, "settings", get_settings())
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            forwarded_ip = forwarded_for.split(",", maxsplit=1)[0].strip()
            if forwarded_ip:
                return forwarded_ip

    if request.client is not None:
        return request.client.host
    return None


def extract_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("User-Agent")
    return user_agent.strip() if user_agent else None
