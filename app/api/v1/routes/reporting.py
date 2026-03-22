"""Reporting and search routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.cases import CaseResponse
from app.api.v1.schemas.reporting import CaseSummaryReportResponse
from app.application.services.reporting import ReportingService
from app.infrastructure.db.session import get_db_session

reports_router = APIRouter(prefix="/reports")
search_router = APIRouter(prefix="/search")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]
SEARCH_QUERY = Query(min_length=2, max_length=120)
SEARCH_LIMIT_QUERY = Query(default=20, ge=1, le=100)


@reports_router.get("/cases/summary", response_model=CaseSummaryReportResponse)
async def get_case_summary_report(
    actor: CurrentActorDep,
    session: SessionDep,
) -> CaseSummaryReportResponse:
    summary = ReportingService(session).case_summary(actor=actor)
    return CaseSummaryReportResponse.model_validate(summary)


@search_router.get("/cases", response_model=list[CaseResponse])
async def search_cases(
    actor: CurrentActorDep,
    session: SessionDep,
    q: str = SEARCH_QUERY,
    limit: int = SEARCH_LIMIT_QUERY,
) -> list[CaseResponse]:
    cases = ReportingService(session).search_cases(actor=actor, query=q, limit=limit)
    return [CaseResponse.model_validate(case, from_attributes=True) for case in cases]
