"""Organization management routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.organizations import InvitationCreateRequest, InvitationCreateResponse
from app.application.services.invitations import InvitationService
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/organizations/current")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


@router.post(
    "/invitations",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    payload: InvitationCreateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> InvitationCreateResponse:
    result = InvitationService(session).create_invitation(actor=actor, payload=payload)
    return InvitationCreateResponse(
        invitation=result.invitation,
        invitation_token=result.invitation_token,
    )
