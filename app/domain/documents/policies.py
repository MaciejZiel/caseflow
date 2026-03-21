"""Policies for document access and mutations."""

from __future__ import annotations

from app.domain.organizations.models import OrganizationRole

DOCUMENT_READ_ROLES = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.MANAGER,
        OrganizationRole.REVIEWER,
        OrganizationRole.MEMBER,
    }
)
DOCUMENT_WRITE_ROLES = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.MANAGER,
        OrganizationRole.MEMBER,
    }
)
DOCUMENT_REVIEW_ROLES = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.MANAGER,
        OrganizationRole.REVIEWER,
    }
)
