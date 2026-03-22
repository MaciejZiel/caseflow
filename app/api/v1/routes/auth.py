"""Authentication routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.auth import (
    AuthResponse,
    AuthSessionInfoResponse,
    LoginRequest,
    OperationStatusResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    RegistrationRequest,
    SessionResponse,
)
from app.api.v1.schemas.organizations import InvitationAcceptRequest
from app.application.services.auth import AuthClientContext, AuthService
from app.application.services.invitations import InvitationService
from app.infrastructure.db.session import get_db_session

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


@router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_organization_owner(
    payload: RegistrationRequest,
    session: SessionDep,
    request: Request,
) -> AuthResponse:
    result = AuthService(session).register_organization_owner(
        payload,
        client_context=_build_client_context(request),
    )
    return AuthResponse.model_validate(result)


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, session: SessionDep, request: Request) -> AuthResponse:
    result = AuthService(session).login(payload, client_context=_build_client_context(request))
    return AuthResponse.model_validate(result)


@router.post("/auth/refresh", response_model=AuthResponse)
async def refresh_session(
    payload: RefreshTokenRequest,
    session: SessionDep,
    request: Request,
) -> AuthResponse:
    result = AuthService(session).refresh_session(
        payload,
        client_context=_build_client_context(request),
    )
    return AuthResponse.model_validate(result)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(actor: CurrentActorDep, session: SessionDep) -> None:
    AuthService(session).logout_current_session(auth_session=actor.auth_session)


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(actor: CurrentActorDep, session: SessionDep) -> None:
    AuthService(session).logout_all_sessions(user=actor.user)


@router.post(
    "/auth/invitations/accept",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invitation(
    payload: InvitationAcceptRequest,
    session: SessionDep,
    request: Request,
) -> AuthResponse:
    result = InvitationService(session).accept_invitation(
        payload,
        client_context=_build_client_context(request),
    )
    return AuthResponse.model_validate(result)


@router.post(
    "/auth/password-reset/request",
    response_model=OperationStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(
    payload: PasswordResetRequest,
    session: SessionDep,
) -> OperationStatusResponse:
    result = AuthService(session).request_password_reset(payload)
    return OperationStatusResponse(status=result.status)


@router.post(
    "/auth/password-reset/confirm",
    response_model=OperationStatusResponse,
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    session: SessionDep,
) -> OperationStatusResponse:
    result = AuthService(session).confirm_password_reset(payload)
    return OperationStatusResponse(status=result.status)


@router.get("/me", response_model=SessionResponse)
async def get_me(actor: CurrentActorDep) -> SessionResponse:
    return SessionResponse.model_validate(
        {
            "user": actor.user,
            "organization": actor.organization,
            "membership": actor.membership,
        }
    )


@router.get("/auth/sessions", response_model=list[AuthSessionInfoResponse])
async def list_auth_sessions(
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[AuthSessionInfoResponse]:
    auth_sessions = AuthService(session).list_user_sessions(user=actor.user)
    return [
        AuthSessionInfoResponse(
            id=auth_session.id,
            organization=auth_session.organization,
            role=auth_session.membership.role,
            client_ip=auth_session.client_ip,
            user_agent=auth_session.user_agent,
            refresh_token_expires_at=auth_session.refresh_token_expires_at,
            last_refreshed_at=auth_session.last_refreshed_at,
            revoked_at=auth_session.revoked_at,
            revoke_reason=auth_session.revoke_reason,
            created_at=auth_session.created_at,
            is_current=actor.auth_session is not None and auth_session.id == actor.auth_session.id,
        )
        for auth_session in auth_sessions
    ]


@router.delete("/auth/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_auth_session(
    session_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> None:
    AuthService(session).revoke_session(user=actor.user, session_id=session_id)


def _build_client_context(request: Request) -> AuthClientContext:
    forwarded_for = request.headers.get("X-Forwarded-For")
    client_ip = forwarded_for.split(",", maxsplit=1)[0].strip() if forwarded_for else None
    if client_ip is None and request.client is not None:
        client_ip = request.client.host
    user_agent = request.headers.get("User-Agent")
    return AuthClientContext(
        client_ip=client_ip or None,
        user_agent=user_agent.strip() if user_agent else None,
    )
