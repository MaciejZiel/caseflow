"""JWT helpers for API authentication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.core.config import get_settings
from app.core.errors import AuthenticationError

JWT_ALGORITHM = "HS256"


def create_access_token(*, user_id: UUID, organization_id: UUID, role: str) -> tuple[str, int]:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    expires_in = settings.access_token_ttl_minutes * 60
    expires_at = issued_at + timedelta(seconds=expires_in)
    payload = {
        "sub": str(user_id),
        "organization_id": str(organization_id),
        "role": role,
        "type": "access",
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, str]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid or expired.") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Token type is invalid.")
    return payload
