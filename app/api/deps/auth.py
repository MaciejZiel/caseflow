"""Authentication-related API dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AuthenticationError
from app.domain.organizations.models import Organization, OrganizationMembership
from app.domain.users.models import User
from app.infrastructure.db.session import get_db_session
from app.infrastructure.security.tokens import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
SessionDep = Annotated[Session, Depends(get_db_session)]


@dataclass(slots=True)
class CurrentActor:
    user: User
    membership: OrganizationMembership

    @property
    def organization(self) -> Organization:
        return self.membership.organization

async def get_current_actor(
    credentials: CredentialsDep,
    session: SessionDep,
) -> CurrentActor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Authentication credentials were not provided.")

    payload = decode_access_token(credentials.credentials)
    user_id = UUID(payload["sub"])
    organization_id = UUID(payload["organization_id"])

    membership = session.scalar(
        select(OrganizationMembership)
        .options(
            joinedload(OrganizationMembership.organization),
            joinedload(OrganizationMembership.user),
        )
        .join(OrganizationMembership.user)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active.is_(True),
            User.is_active.is_(True),
        )
    )
    if membership is None:
        raise AuthenticationError("Authentication context is invalid or no longer active.")

    return CurrentActor(user=membership.user, membership=membership)
