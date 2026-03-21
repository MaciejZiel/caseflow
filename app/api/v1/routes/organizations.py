"""Organization management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.organizations import (
    InvitationCreateRequest,
    InvitationCreateResponse,
    OrganizationContextResponse,
    OrganizationMemberResponse,
    OrganizationMemberUpdateRequest,
)
from app.application.services.invitations import InvitationService
from app.application.services.organizations import OrganizationService
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/organizations/current")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


@router.get("", response_model=OrganizationContextResponse)
async def get_current_organization(actor: CurrentActorDep) -> OrganizationContextResponse:
    return OrganizationContextResponse(
        organization=actor.organization,
        membership=actor.membership,
    )


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


@router.get("/members", response_model=list[OrganizationMemberResponse])
async def list_members(
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[OrganizationMemberResponse]:
    memberships = OrganizationService(session).list_members(actor=actor)
    return [
        OrganizationMemberResponse.model_validate(membership, from_attributes=True)
        for membership in memberships
    ]


@router.patch("/members/{member_id}", response_model=OrganizationMemberResponse)
async def update_member(
    member_id: UUID,
    payload: OrganizationMemberUpdateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> OrganizationMemberResponse:
    membership = OrganizationService(session).update_member(
        actor=actor,
        member_id=member_id,
        payload=payload,
    )
    return OrganizationMemberResponse.model_validate(membership, from_attributes=True)
