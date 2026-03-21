"""Authentication and registration use cases."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.v1.schemas.auth import LoginRequest, RegistrationRequest
from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, DomainValidationError
from app.domain.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
)
from app.domain.users.models import User
from app.infrastructure.security.passwords import hash_password, verify_password
from app.infrastructure.security.tokens import create_access_token


@dataclass(slots=True)
class AuthResult:
    access_token: str
    token_type: str
    expires_in: int
    user: User
    organization: Organization
    membership: OrganizationMembership


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register_organization_owner(self, payload: RegistrationRequest) -> AuthResult:
        if self._email_exists(payload.email):
            raise ConflictError("email_already_in_use", "A user with this email already exists.")
        if self._organization_slug_exists(payload.organization_slug):
            raise ConflictError(
                "organization_slug_taken",
                "This organization slug is already in use.",
            )

        organization = Organization(
            name=payload.organization_name,
            slug=payload.organization_slug,
            status=OrganizationStatus.ACTIVE,
        )
        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
        membership = OrganizationMembership(
            organization=organization,
            user=user,
            role=OrganizationRole.OWNER,
        )

        try:
            self.session.add_all([organization, user, membership])
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "registration_conflict",
                "Registration could not be completed because of a conflicting record.",
            ) from exc

        self.session.refresh(membership)
        self.session.refresh(user)
        self.session.refresh(organization)
        return build_auth_result(user=user, organization=organization, membership=membership)

    def login(self, payload: LoginRequest) -> AuthResult:
        user = self.session.scalar(select(User).where(User.email == payload.email))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationError("User account is inactive.")

        membership = self._resolve_membership(
            user_id=user.id,
            organization_slug=payload.organization_slug,
        )
        if membership is None:
            raise AuthenticationError("No active organization membership was found for this user.")
        if membership.organization.status is not OrganizationStatus.ACTIVE:
            raise AuthenticationError("Selected organization is not active.")

        return build_auth_result(
            user=user,
            organization=membership.organization,
            membership=membership,
        )

    def _resolve_membership(
        self,
        *,
        user_id: UUID,
        organization_slug: str | None,
    ) -> OrganizationMembership | None:
        query = (
            select(OrganizationMembership)
            .options(joinedload(OrganizationMembership.organization))
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.is_active.is_(True),
            )
            .order_by(OrganizationMembership.joined_at.asc())
        )

        if organization_slug is not None:
            query = query.join(OrganizationMembership.organization).where(
                Organization.slug == organization_slug
            )
            return self.session.scalar(query)

        memberships = list(self.session.scalars(query))
        if not memberships:
            return None
        if len(memberships) > 1:
            raise DomainValidationError(
                "organization_selection_required",
                "Provide organization_slug when the user belongs to multiple organizations.",
            )
        return memberships[0]

    def _email_exists(self, email: str) -> bool:
        return self.session.scalar(select(User.id).where(User.email == email)) is not None

    def _organization_slug_exists(self, slug: str) -> bool:
        return (
            self.session.scalar(select(Organization.id).where(Organization.slug == slug))
            is not None
        )


def build_auth_result(
    *,
    user: User,
    organization: Organization,
    membership: OrganizationMembership,
) -> AuthResult:
    settings = get_settings()
    token, expires_in = create_access_token(
        user_id=user.id,
        organization_id=organization.id,
        role=membership.role.value,
    )
    return AuthResult(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in or settings.access_token_ttl_minutes * 60,
        user=user,
        organization=organization,
        membership=membership,
    )
