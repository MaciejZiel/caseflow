"""Authentication routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RegistrationRequest,
    SessionResponse,
)
from app.api.v1.schemas.organizations import InvitationAcceptRequest
from app.application.services.auth import AuthService
from app.application.services.invitations import InvitationService
from app.infrastructure.db.session import get_db_session

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


@router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_organization_owner(
    payload: RegistrationRequest,
    session: SessionDep,
) -> AuthResponse:
    result = AuthService(session).register_organization_owner(payload)
    return AuthResponse.model_validate(result)


@router.post("/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest, session: SessionDep) -> AuthResponse:
    result = AuthService(session).login(payload)
    return AuthResponse.model_validate(result)


@router.post(
    "/auth/invitations/accept",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invitation(
    payload: InvitationAcceptRequest,
    session: SessionDep,
) -> AuthResponse:
    result = InvitationService(session).accept_invitation(payload)
    return AuthResponse.model_validate(result)


@router.get("/me", response_model=SessionResponse)
async def get_me(actor: CurrentActorDep) -> SessionResponse:
    return SessionResponse.model_validate(
        {
            "user": actor.user,
            "organization": actor.organization,
            "membership": actor.membership,
        }
    )
