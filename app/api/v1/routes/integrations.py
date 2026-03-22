"""Read-only integration routes backed by organization API keys."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps.api_keys import require_api_key
from app.api.v1.schemas.cases import CaseResponse
from app.api.v1.schemas.documents import DocumentResponse
from app.application.services.api_keys import ApiKeyContext, ApiKeyService
from app.application.services.reporting import ReportingService
from app.domain.api_keys.models import ApiKeyScope
from app.domain.cases.models import CaseStatus
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/integrations")
SessionDep = Annotated[Session, Depends(get_db_session)]
CasesApiKeyDep = Annotated[ApiKeyContext, Depends(require_api_key(ApiKeyScope.CASES_READ))]
DocumentsApiKeyDep = Annotated[
    ApiKeyContext,
    Depends(require_api_key(ApiKeyScope.DOCUMENTS_READ)),
]
LIMIT_QUERY = Query(default=50, ge=1, le=200)
STATUS_QUERY = Query(default=None)
EXTERNAL_ID_QUERY = Query(default=None, max_length=120)
UPDATED_AFTER_QUERY = Query(default=None)
EXPORT_LIMIT_QUERY = Query(default=1000, ge=1, le=5000)


@router.get("/cases", response_model=list[CaseResponse])
async def list_cases(
    api_key: CasesApiKeyDep,
    session: SessionDep,
    limit: int = LIMIT_QUERY,
    status: CaseStatus | None = STATUS_QUERY,
    external_id: str | None = EXTERNAL_ID_QUERY,
    updated_after: datetime | None = UPDATED_AFTER_QUERY,
) -> list[CaseResponse]:
    cases = ApiKeyService(session).list_cases_for_integration(
        api_key=api_key,
        limit=limit,
        status=status,
        external_id=external_id,
        updated_after=updated_after,
    )
    return [CaseResponse.model_validate(case, from_attributes=True) for case in cases]


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    api_key: CasesApiKeyDep,
    session: SessionDep,
) -> CaseResponse:
    case = ApiKeyService(session).get_case_for_integration(api_key=api_key, case_id=case_id)
    return CaseResponse.model_validate(case, from_attributes=True)


@router.get("/cases/{case_id}/documents", response_model=list[DocumentResponse])
async def list_case_documents(
    case_id: UUID,
    api_key: DocumentsApiKeyDep,
    session: SessionDep,
) -> list[DocumentResponse]:
    documents = ApiKeyService(session).list_case_documents_for_integration(
        api_key=api_key,
        case_id=case_id,
    )
    return [
        DocumentResponse.model_validate(document, from_attributes=True)
        for document in documents
    ]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    api_key: DocumentsApiKeyDep,
    session: SessionDep,
) -> DocumentResponse:
    document = ApiKeyService(session).get_document_for_integration(
        api_key=api_key,
        document_id=document_id,
    )
    return DocumentResponse.model_validate(document, from_attributes=True)


@router.get("/exports/cases.csv", response_class=PlainTextResponse)
async def export_cases_csv(
    api_key: CasesApiKeyDep,
    session: SessionDep,
    limit: int = EXPORT_LIMIT_QUERY,
    status: CaseStatus | None = STATUS_QUERY,
    external_id: str | None = EXTERNAL_ID_QUERY,
    updated_after: datetime | None = UPDATED_AFTER_QUERY,
) -> PlainTextResponse:
    csv_payload = ReportingService(session).export_cases_csv(
        api_key=api_key,
        limit=limit,
        status=status,
        external_id=external_id,
        updated_after=updated_after,
    )
    return PlainTextResponse(
        content=csv_payload,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cases-export.csv"'},
    )
