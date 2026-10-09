"""Organization context and membership management services."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.v1.schemas.organizations import OrganizationMemberUpdateRequest
from app.application.actors import ActorContext
from app.core.errors import DomainValidationError, NotFoundError
from app.domain.organizations.models import OrganizationMembership, OrganizationRole
from app.domain.organizations.policies import (
    MEMBER_MANAGER_ROLES,
    MEMBER_VIEWER_ROLES,
    ensure_role_allowed,
)


class OrganizationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_members(self, *, actor: ActorContext) -> list[OrganizationMembership]:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=MEMBER_VIEWER_ROLES,
            message="Only owners and admins can view organization members.",
        )
        return list(
            self.session.scalars(
                select(OrganizationMembership)
                .options(joinedload(OrganizationMembership.user))
                .where(OrganizationMembership.organization_id == actor.organization.id)
                .order_by(OrganizationMembership.joined_at.asc())
            )
        )

    def update_member(
        self,
        *,
        actor: ActorContext,
        member_id: UUID,
        payload: OrganizationMemberUpdateRequest,
    ) -> OrganizationMembership:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=MEMBER_MANAGER_ROLES,
            message="Only owners and admins can manage organization members.",
        )
        target = self.session.scalar(
            select(OrganizationMembership)
            .options(joinedload(OrganizationMembership.user))
            .where(
                OrganizationMembership.id == member_id,
                OrganizationMembership.organization_id == actor.organization.id,
            )
        )
        if target is None:
            raise NotFoundError(
                "organization_member",
                "Organization member does not exist.",
            )

        self._validate_member_update(actor=actor, target=target, payload=payload)

        if payload.role is not None:
            target.role = payload.role
        if payload.is_active is not None:
            target.is_active = payload.is_active

        self.session.commit()
        self.session.refresh(target)
        return target

    def _validate_member_update(
        self,
        *,
        actor: ActorContext,
        target: OrganizationMembership,
        payload: OrganizationMemberUpdateRequest,
    ) -> None:
        is_self_update = target.id == actor.membership.id
        actor_role = actor.membership.role

        if actor_role == OrganizationRole.ADMIN and target.role == OrganizationRole.OWNER:
            raise DomainValidationError(
                "owner_member_update_forbidden",
                "Admins cannot modify owner memberships.",
            )
        if actor_role == OrganizationRole.ADMIN and payload.role == OrganizationRole.OWNER:
            raise DomainValidationError(
                "owner_assignment_forbidden",
                "Admins cannot assign the owner role.",
            )
        if is_self_update and payload.is_active is False:
            raise DomainValidationError(
                "self_deactivation_forbidden",
                "You cannot deactivate your own membership.",
            )
        if is_self_update and payload.role is not None and payload.role != target.role:
            raise DomainValidationError(
                "self_role_change_forbidden",
                "You cannot change your own role.",
            )
        if target.role == OrganizationRole.OWNER and payload.is_active is False:
            self._ensure_not_disabling_last_owner(target)
        if target.role == OrganizationRole.OWNER and payload.role not in (
            None,
            OrganizationRole.OWNER,
        ):
            self._ensure_not_demoting_last_owner(target)

    def _ensure_not_disabling_last_owner(self, target: OrganizationMembership) -> None:
        active_owner_count = self._count_active_owners(target.organization_id)
        if active_owner_count <= 1:
            raise DomainValidationError(
                "last_owner_deactivation_forbidden",
                "You cannot deactivate the last active owner.",
            )

    def _ensure_not_demoting_last_owner(self, target: OrganizationMembership) -> None:
        active_owner_count = self._count_active_owners(target.organization_id)
        if active_owner_count <= 1:
            raise DomainValidationError(
                "last_owner_demotion_forbidden",
                "You cannot change the role of the last active owner.",
            )

    def _count_active_owners(self, organization_id: UUID) -> int:
        return int(
            self.session.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == OrganizationRole.OWNER,
                    OrganizationMembership.is_active.is_(True),
                )
            )
            or 0
        )
