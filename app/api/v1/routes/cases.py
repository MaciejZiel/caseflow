"""Case management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.cases import CaseCreateRequest, CaseResponse, CaseUpdateRequest
from app.application.services.cases import CaseService
from app.domain.cases.models import CasePriority, CaseStatus
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/cases")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]
LIMIT_QUERY = Query(default=20, ge=1, le=100)
OFFSET_QUERY = Query(default=0, ge=0)
STATUS_QUERY = Query(default=None)
PRIORITY_QUERY = Query(default=None)


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> CaseResponse:
    case = CaseService(session).create_case(actor=actor, payload=payload)
    return CaseResponse.model_validate(case, from_attributes=True)


@router.get("", response_model=list[CaseResponse])
async def list_cases(
    actor: CurrentActorDep,
    session: SessionDep,
    limit: int = LIMIT_QUERY,
    offset: int = OFFSET_QUERY,
    status: CaseStatus | None = STATUS_QUERY,
    priority: CasePriority | None = PRIORITY_QUERY,
) -> list[CaseResponse]:
    cases = CaseService(session).list_cases(
        actor=actor,
        limit=limit,
        offset=offset,
        status=status,
        priority=priority,
    )
    return [CaseResponse.model_validate(case, from_attributes=True) for case in cases]


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> CaseResponse:
    case = CaseService(session).get_case(actor=actor, case_id=case_id)
    return CaseResponse.model_validate(case, from_attributes=True)


@router.patch("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: UUID,
    payload: CaseUpdateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> CaseResponse:
    case = CaseService(session).update_case(
        actor=actor,
        case_id=case_id,
        payload=payload,
    )
    return CaseResponse.model_validate(case, from_attributes=True)


@router.post("/{case_id}/archive", response_model=CaseResponse)
async def archive_case(
    case_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> CaseResponse:
    case = CaseService(session).archive_case(actor=actor, case_id=case_id)
    return CaseResponse.model_validate(case, from_attributes=True)
