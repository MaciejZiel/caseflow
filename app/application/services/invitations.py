"""Invitation creation and acceptance workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.v1.schemas.organizations import InvitationAcceptRequest, InvitationCreateRequest
from app.application.actors import ActorContext
from app.application.services.auth import (
    AuthClientContext,
    AuthResult,
    build_auth_result,
    create_auth_session,
)
from app.core.config import get_settings
from app.core.errors import ConflictError, DomainValidationError
from app.domain.organizations.models import Invitation, OrganizationMembership, OrganizationRole
from app.domain.organizations.policies import INVITATION_MANAGER_ROLES, ensure_role_allowed
from app.domain.users.models import User
from app.infrastructure.security.invitations import generate_invitation_token, hash_invitation_token
from app.infrastructure.security.passwords import hash_password


@dataclass(slots=True)
class InvitationCreateResult:
    invitation: Invitation
    invitation_token: str


class InvitationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def create_invitation(
        self,
        *,
        actor: ActorContext,
        payload: InvitationCreateRequest,
    ) -> InvitationCreateResult:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=INVITATION_MANAGER_ROLES,
            message="Only owners and admins can invite organization members.",
        )
        if (
            payload.role == OrganizationRole.OWNER
            and actor.membership.role != OrganizationRole.OWNER
        ):
            raise DomainValidationError(
                "owner_invitation_forbidden",
                "Only an owner can invite another owner.",
            )
        self._ensure_email_not_already_assigned(actor=actor, email=payload.email)
        self._ensure_no_active_invitation(actor=actor, email=payload.email)

        raw_token = generate_invitation_token()
        invitation = Invitation(
            organization_id=actor.organization.id,
            email=payload.email,
            role=payload.role,
            token_hash=hash_invitation_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=self.settings.invitation_ttl_hours),
            invited_by_user_id=actor.user.id,
        )

        self.session.add(invitation)
        self.session.commit()
        self.session.refresh(invitation)
        return InvitationCreateResult(invitation=invitation, invitation_token=raw_token)

    def accept_invitation(
        self,
        payload: InvitationAcceptRequest,
        *,
        client_context: AuthClientContext | None = None,
    ) -> AuthResult:
        invitation = self.session.scalar(
            select(Invitation)
            .options(joinedload(Invitation.organization))
            .where(Invitation.token_hash == hash_invitation_token(payload.token))
        )
        if invitation is None:
            raise DomainValidationError(
                "invalid_invitation_token",
                "Invitation token is invalid.",
            )
        if invitation.accepted_at is not None:
            raise DomainValidationError(
                "invitation_already_accepted",
                "This invitation has already been accepted.",
            )
        if _to_utc(invitation.expires_at) < datetime.now(UTC):
            raise DomainValidationError(
                "invitation_expired",
                "This invitation has expired.",
            )

        existing_user = self.session.scalar(select(User).where(User.email == invitation.email))
        if existing_user is not None:
            raise ConflictError(
                "email_already_in_use",
                "A user with this email already exists.",
            )

        user = User(
            email=invitation.email,
            password_hash=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
        membership = OrganizationMembership(
            organization_id=invitation.organization_id,
            user=user,
            role=invitation.role,
        )
        invitation.accepted_at = datetime.now(UTC)
        auth_session, refresh_token = create_auth_session(
            user=user,
            organization=invitation.organization,
            membership=membership,
            settings=self.settings,
            client_context=client_context,
        )
        user.last_login_at = datetime.now(UTC)

        try:
            self.session.add_all([user, membership, auth_session])
            self.session.flush()
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "invitation_accept_conflict",
                "Invitation could not be accepted because of a conflicting record.",
            ) from exc

        self.session.refresh(invitation)
        self.session.refresh(user)
        self.session.refresh(membership)
        return build_auth_result(
            user=user,
            organization=invitation.organization,
            membership=membership,
            auth_session=auth_session,
            refresh_token=refresh_token,
            settings=self.settings,
        )

    def _ensure_email_not_already_assigned(self, *, actor: ActorContext, email: str) -> None:
        membership = self.session.scalar(
            select(OrganizationMembership)
            .join(OrganizationMembership.user)
            .where(
                OrganizationMembership.organization_id == actor.organization.id,
                User.email == email,
                OrganizationMembership.is_active.is_(True),
            )
        )
        if membership is not None:
            raise ConflictError(
                "member_already_exists",
                "This user is already an active member of the organization.",
            )

    def _ensure_no_active_invitation(self, *, actor: ActorContext, email: str) -> None:
        pending_invitation = self.session.scalar(
            select(Invitation.id).where(
                Invitation.organization_id == actor.organization.id,
                Invitation.email == email,
                Invitation.accepted_at.is_(None),
                Invitation.expires_at >= datetime.now(UTC),
            )
        )
        if pending_invitation is not None:
            raise ConflictError(
                "invitation_already_pending",
                "A pending invitation already exists for this email.",
            )


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
