"""Dependencies for API key-authenticated integration access."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.application.services.api_keys import ApiKeyContext, ApiKeyService
from app.domain.api_keys.models import ApiKeyScope
from app.infrastructure.db.session import get_db_session

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
ApiKeyHeaderDep = Annotated[str | None, Depends(api_key_scheme)]
SessionDep = Annotated[Session, Depends(get_db_session)]


def require_api_key(*required_scopes: ApiKeyScope) -> Callable[..., ApiKeyContext]:
    async def dependency(
        raw_key: ApiKeyHeaderDep,
        session: SessionDep,
        request: Request,
    ) -> ApiKeyContext:
        if raw_key is None or not raw_key.strip():
            from app.core.errors import AuthenticationError

            raise AuthenticationError("API key was not provided.")
        return ApiKeyService(session).authenticate_api_key(
            raw_key=raw_key.strip(),
            client_ip=_extract_client_ip(request),
            required_scopes=set(required_scopes),
        )

    return dependency


def _extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    client_ip = forwarded_for.split(",", maxsplit=1)[0].strip() if forwarded_for else None
    if client_ip is None and request.client is not None:
        client_ip = request.client.host
    return client_ip or None
