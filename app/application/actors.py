"""Application-level actor context objects."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.auth.models import AuthSession
from app.domain.organizations.models import Organization, OrganizationMembership
from app.domain.users.models import User


@dataclass(slots=True)
class ActorContext:
    user: User
    membership: OrganizationMembership
    auth_session: AuthSession | None = None

    @property
    def organization(self) -> Organization:
        return self.membership.organization
