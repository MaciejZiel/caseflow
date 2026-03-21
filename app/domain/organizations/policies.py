"""Role-based policies for organization actions."""

from __future__ import annotations

from collections.abc import Iterable

from app.core.errors import PermissionDeniedError
from app.domain.organizations.models import OrganizationRole

INVITATION_MANAGER_ROLES = frozenset({OrganizationRole.OWNER, OrganizationRole.ADMIN})
MEMBER_VIEWER_ROLES = frozenset({OrganizationRole.OWNER, OrganizationRole.ADMIN})
MEMBER_MANAGER_ROLES = frozenset({OrganizationRole.OWNER, OrganizationRole.ADMIN})


def ensure_role_allowed(
    actor_role: OrganizationRole,
    *,
    allowed_roles: Iterable[OrganizationRole],
    message: str,
) -> None:
    if actor_role not in set(allowed_roles):
        raise PermissionDeniedError(message)
