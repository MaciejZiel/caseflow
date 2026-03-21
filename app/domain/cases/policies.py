"""Policies for case access and mutations."""

from __future__ import annotations

from app.domain.organizations.models import OrganizationRole

CASE_READ_ROLES = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.MANAGER,
        OrganizationRole.REVIEWER,
        OrganizationRole.MEMBER,
    }
)
CASE_WRITE_ROLES = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.MANAGER,
        OrganizationRole.MEMBER,
    }
)
