"""Authentication and registration use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.v1.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    RegistrationRequest,
)
from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError, DomainValidationError, NotFoundError
from app.domain.auth.models import AuthSession, PasswordResetToken
from app.domain.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationRole,
    OrganizationStatus,
)
from app.domain.users.models import User
from app.infrastructure.security.opaque_tokens import generate_opaque_token, hash_opaque_token
from app.infrastructure.security.passwords import hash_password, verify_password
from app.infrastructure.security.tokens import create_access_token


@dataclass(slots=True)
class AuthClientContext:
    client_ip: str | None
    user_agent: str | None


@dataclass(slots=True)
class AuthResult:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_token_expires_in: int
    user: User
    organization: Organization
    membership: OrganizationMembership


@dataclass(slots=True)
class OperationStatusResult:
    status: str


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()

    def register_organization_owner(
        self,
        payload: RegistrationRequest,
        *,
        client_context: AuthClientContext | None = None,
    ) -> AuthResult:
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
        auth_session, refresh_token = create_auth_session(
            user=user,
            organization=organization,
            membership=membership,
            settings=self.settings,
            client_context=client_context,
        )
        issued_at = datetime.now(UTC)
        user.last_login_at = issued_at

        try:
            self.session.add_all([organization, user, membership, auth_session])
            self.session.flush()
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
        return build_auth_result(
            user=user,
            organization=organization,
            membership=membership,
            auth_session=auth_session,
            refresh_token=refresh_token,
            settings=self.settings,
        )

    def login(
        self,
        payload: LoginRequest,
        *,
        client_context: AuthClientContext | None = None,
    ) -> AuthResult:
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

        auth_session, refresh_token = create_auth_session(
            user=user,
            organization=membership.organization,
            membership=membership,
            settings=self.settings,
            client_context=client_context,
        )
        user.last_login_at = datetime.now(UTC)
        self.session.add(auth_session)
        self.session.flush()
        self.session.commit()

        return build_auth_result(
            user=user,
            organization=membership.organization,
            membership=membership,
            auth_session=auth_session,
            refresh_token=refresh_token,
            settings=self.settings,
        )

    def refresh_session(
        self,
        payload: RefreshTokenRequest,
        *,
        client_context: AuthClientContext | None = None,
    ) -> AuthResult:
        auth_session = self.session.scalar(
            select(AuthSession)
            .options(
                joinedload(AuthSession.user),
                joinedload(AuthSession.organization),
                joinedload(AuthSession.membership).joinedload(OrganizationMembership.organization),
            )
            .where(AuthSession.refresh_token_hash == hash_opaque_token(payload.refresh_token))
        )
        if auth_session is None:
            raise AuthenticationError("Refresh token is invalid or expired.")

        self._ensure_auth_session_is_active(auth_session)

        refresh_token = rotate_auth_session(
            auth_session=auth_session,
            settings=self.settings,
            client_context=client_context,
        )
        auth_session.user.last_login_at = datetime.now(UTC)
        self.session.commit()

        return build_auth_result(
            user=auth_session.user,
            organization=auth_session.organization,
            membership=auth_session.membership,
            auth_session=auth_session,
            refresh_token=refresh_token,
            settings=self.settings,
        )

    def logout_current_session(self, *, auth_session: AuthSession) -> None:
        if auth_session.revoked_at is not None:
            return
        auth_session.revoked_at = datetime.now(UTC)
        auth_session.revoke_reason = "user_logout"
        self.session.commit()

    def logout_all_sessions(self, *, user: User) -> None:
        now = datetime.now(UTC)
        active_sessions = self.session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
            )
        )
        for auth_session in active_sessions:
            auth_session.revoked_at = now
            auth_session.revoke_reason = "logout_all"
        self.session.commit()

    def list_user_sessions(
        self,
        *,
        user: User,
    ) -> list[AuthSession]:
        return list(
            self.session.scalars(
                select(AuthSession)
                .options(
                    joinedload(AuthSession.organization),
                    joinedload(AuthSession.membership),
                )
                .where(AuthSession.user_id == user.id)
                .order_by(
                    AuthSession.revoked_at.is_not(None).asc(),
                    AuthSession.created_at.desc(),
                )
            )
        )

    def revoke_session(
        self,
        *,
        user: User,
        session_id: UUID,
    ) -> AuthSession:
        auth_session = self.session.scalar(
            select(AuthSession)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user.id,
            )
        )
        if auth_session is None:
            raise NotFoundError("auth_session", "Authentication session does not exist.")
        if auth_session.revoked_at is None:
            auth_session.revoked_at = datetime.now(UTC)
            auth_session.revoke_reason = "session_revoked"
            self.session.commit()
        return auth_session

    def request_password_reset(self, payload: PasswordResetRequest) -> OperationStatusResult:
        user = self.session.scalar(select(User).where(User.email == payload.email))
        if user is None or not user.is_active:
            return OperationStatusResult(status="accepted")

        now = datetime.now(UTC)
        active_tokens = self.session.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.consumed_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
            )
        )
        for token in active_tokens:
            token.revoked_at = now

        raw_token = generate_opaque_token()
        password_reset = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=now + timedelta(minutes=self.settings.password_reset_ttl_minutes),
        )
        self.session.add(password_reset)
        self.session.commit()
        return OperationStatusResult(status="accepted")

    def confirm_password_reset(
        self,
        payload: PasswordResetConfirmRequest,
    ) -> OperationStatusResult:
        reset_token = self.session.scalar(
            select(PasswordResetToken)
            .options(joinedload(PasswordResetToken.user))
            .where(PasswordResetToken.token_hash == hash_opaque_token(payload.token))
        )
        if reset_token is None:
            raise DomainValidationError(
                "invalid_password_reset_token",
                "Password reset token is invalid.",
            )
        if reset_token.revoked_at is not None or reset_token.consumed_at is not None:
            raise DomainValidationError(
                "password_reset_token_inactive",
                "Password reset token is no longer active.",
            )
        if _to_utc(reset_token.expires_at) < datetime.now(UTC):
            raise DomainValidationError(
                "password_reset_token_expired",
                "Password reset token has expired.",
            )
        if not reset_token.user.is_active:
            raise AuthenticationError("User account is inactive.")

        reset_token.user.password_hash = hash_password(payload.password)
        reset_token.consumed_at = datetime.now(UTC)
        self._revoke_user_sessions(
            user_id=reset_token.user.id,
            reason="password_reset",
        )

        active_tokens = self.session.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == reset_token.user.id,
                PasswordResetToken.id != reset_token.id,
                PasswordResetToken.consumed_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
            )
        )
        for token in active_tokens:
            token.revoked_at = datetime.now(UTC)

        self.session.commit()
        return OperationStatusResult(status="password_reset")

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

    def _ensure_auth_session_is_active(self, auth_session: AuthSession) -> None:
        if auth_session.revoked_at is not None:
            raise AuthenticationError("Refresh token is invalid or expired.")
        if _to_utc(auth_session.refresh_token_expires_at) < datetime.now(UTC):
            raise AuthenticationError("Refresh token is invalid or expired.")
        if not auth_session.user.is_active:
            raise AuthenticationError("User account is inactive.")
        if not auth_session.membership.is_active:
            raise AuthenticationError("Organization membership is inactive.")
        if auth_session.organization.status is not OrganizationStatus.ACTIVE:
            raise AuthenticationError("Selected organization is not active.")

    def _revoke_user_sessions(self, *, user_id: UUID, reason: str) -> None:
        now = datetime.now(UTC)
        active_sessions = self.session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        for auth_session in active_sessions:
            auth_session.revoked_at = now
            auth_session.revoke_reason = reason


def build_auth_result(
    *,
    user: User,
    organization: Organization,
    membership: OrganizationMembership,
    auth_session: AuthSession,
    refresh_token: str,
    settings=None,
) -> AuthResult:
    settings = settings or get_settings()
    token, expires_in = create_access_token(
        user_id=user.id,
        organization_id=organization.id,
        role=membership.role.value,
        session_id=auth_session.id,
    )
    return AuthResult(
        access_token=token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in or settings.access_token_ttl_minutes * 60,
        refresh_token_expires_in=settings.refresh_token_ttl_days * 24 * 60 * 60,
        user=user,
        organization=organization,
        membership=membership,
    )


def create_auth_session(
    *,
    user: User,
    organization: Organization,
    membership: OrganizationMembership,
    settings=None,
    client_context: AuthClientContext | None = None,
) -> tuple[AuthSession, str]:
    settings = settings or get_settings()
    refresh_token = generate_opaque_token()
    auth_session = AuthSession(
        user=user,
        organization=organization,
        membership=membership,
        refresh_token_hash=hash_opaque_token(refresh_token),
        refresh_token_expires_at=datetime.now(UTC)
        + timedelta(days=settings.refresh_token_ttl_days),
        client_ip=client_context.client_ip if client_context else None,
        user_agent=client_context.user_agent if client_context else None,
    )
    return auth_session, refresh_token


def rotate_auth_session(
    *,
    auth_session: AuthSession,
    settings=None,
    client_context: AuthClientContext | None = None,
) -> str:
    settings = settings or get_settings()
    refresh_token = generate_opaque_token()
    auth_session.refresh_token_hash = hash_opaque_token(refresh_token)
    auth_session.refresh_token_expires_at = datetime.now(UTC) + timedelta(
        days=settings.refresh_token_ttl_days
    )
    auth_session.last_refreshed_at = datetime.now(UTC)
    if client_context is not None:
        auth_session.client_ip = client_context.client_ip
        auth_session.user_agent = client_context.user_agent
    return refresh_token


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
