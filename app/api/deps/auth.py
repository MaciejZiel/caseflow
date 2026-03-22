"""Authentication-related API dependencies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.application.actors import ActorContext
from app.application.services.auth import AuthClientContext, touch_auth_session_activity
from app.core.errors import AuthenticationError
from app.domain.auth.models import AuthSession
from app.domain.organizations.models import OrganizationMembership, OrganizationStatus
from app.infrastructure.db.session import get_db_session
from app.infrastructure.security.tokens import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActor = ActorContext

async def get_current_actor(
    credentials: CredentialsDep,
    session: SessionDep,
    request: Request,
) -> CurrentActor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Authentication credentials were not provided.")

    payload = decode_access_token(credentials.credentials)
    user_id = UUID(payload["sub"])
    organization_id = UUID(payload["organization_id"])
    session_id = _parse_session_id(payload)

    auth_session = session.scalar(
        select(AuthSession)
        .options(
            joinedload(AuthSession.organization),
            joinedload(AuthSession.membership).joinedload(OrganizationMembership.organization),
            joinedload(AuthSession.user),
        )
        .where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.organization_id == organization_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    if auth_session is None:
        raise AuthenticationError("Authentication context is invalid or no longer active.")
    if _to_utc(auth_session.refresh_token_expires_at) < datetime.now(UTC):
        raise AuthenticationError("Authentication context is invalid or no longer active.")
    if not auth_session.user.is_active or not auth_session.membership.is_active:
        raise AuthenticationError("Authentication context is invalid or no longer active.")
    if auth_session.organization.status is not OrganizationStatus.ACTIVE:
        raise AuthenticationError("Authentication context is invalid or no longer active.")

    client_context = build_auth_client_context(request)
    if touch_auth_session_activity(auth_session, client_context=client_context):
        session.commit()

    return CurrentActor(
        user=auth_session.user,
        membership=auth_session.membership,
        auth_session=auth_session,
    )


def _parse_session_id(payload: dict[str, str]) -> UUID:
    raw_session_id = payload.get("session_id")
    if raw_session_id is None:
        raise AuthenticationError("Authentication context is invalid or no longer active.")
    return UUID(raw_session_id)


def build_auth_client_context(request: Request) -> AuthClientContext:
    forwarded_for = request.headers.get("X-Forwarded-For")
    client_ip = forwarded_for.split(",", maxsplit=1)[0].strip() if forwarded_for else None
    if client_ip is None and request.client is not None:
        client_ip = request.client.host
    user_agent = request.headers.get("User-Agent")
    return AuthClientContext(
        client_ip=client_ip or None,
        user_agent=user_agent.strip() if user_agent else None,
    )


def _to_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
