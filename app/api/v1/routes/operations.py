"""Organization-scoped operations routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.operations import (
    OperationsFailureResponse,
    OperationsRetentionPreviewResponse,
    OperationsRetentionRunResponse,
    OperationsRetryDueResponse,
    OperationsSummaryResponse,
)
from app.application.services.operations import OperationsService
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/operations")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]
LIMIT_QUERY = Query(default=20, ge=1, le=100)
RETRY_LIMIT_QUERY = Query(default=25, ge=1, le=200)


@router.get("/summary", response_model=OperationsSummaryResponse)
async def get_operations_summary(
    actor: CurrentActorDep,
    session: SessionDep,
) -> OperationsSummaryResponse:
    summary = OperationsService(session).get_summary(actor=actor)
    return OperationsSummaryResponse.model_validate(summary)


@router.get("/failures", response_model=list[OperationsFailureResponse])
async def list_operations_failures(
    actor: CurrentActorDep,
    session: SessionDep,
    limit: int = LIMIT_QUERY,
) -> list[OperationsFailureResponse]:
    failures = OperationsService(session).list_recent_failures(actor=actor, limit=limit)
    return [
        OperationsFailureResponse.model_validate(item, from_attributes=True)
        for item in failures
    ]


@router.post("/retry-due", response_model=OperationsRetryDueResponse)
async def retry_due_operations(
    actor: CurrentActorDep,
    session: SessionDep,
    limit_per_queue: int = RETRY_LIMIT_QUERY,
) -> OperationsRetryDueResponse:
    result = OperationsService(session).retry_due_items(
        actor=actor,
        limit_per_queue=limit_per_queue,
    )
    return OperationsRetryDueResponse.model_validate(result, from_attributes=True)


@router.get("/retention-preview", response_model=OperationsRetentionPreviewResponse)
async def preview_operations_retention(
    actor: CurrentActorDep,
    session: SessionDep,
) -> OperationsRetentionPreviewResponse:
    result = OperationsService(session).preview_retention_cleanup(actor=actor)
    return OperationsRetentionPreviewResponse.model_validate(result, from_attributes=True)


@router.post("/retention-run", response_model=OperationsRetentionRunResponse)
async def run_operations_retention(
    actor: CurrentActorDep,
    session: SessionDep,
) -> OperationsRetentionRunResponse:
    result = OperationsService(session).run_retention_cleanup(actor=actor)
    return OperationsRetentionRunResponse.model_validate(result, from_attributes=True)
