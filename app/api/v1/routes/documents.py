"""Document upload, versioning and job inspection routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.documents import (
    DocumentResponse,
    DocumentUploadRequest,
    DocumentVersionResponse,
    DocumentVersionUploadRequest,
    ProcessingJobResponse,
)
from app.application.services.documents import DocumentService
from app.infrastructure.db.session import get_db_session

case_router = APIRouter(prefix="/cases")
document_router = APIRouter(prefix="/documents")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


@case_router.post(
    "/{case_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    case_id: UUID,
    payload: DocumentUploadRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> DocumentResponse:
    document = DocumentService(session).create_document(
        actor=actor,
        case_id=case_id,
        payload=payload,
    )
    return DocumentResponse.model_validate(document, from_attributes=True)


@document_router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> DocumentResponse:
    document = DocumentService(session).get_document(actor=actor, document_id=document_id)
    return DocumentResponse.model_validate(document, from_attributes=True)


@document_router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
async def list_document_versions(
    document_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[DocumentVersionResponse]:
    versions = DocumentService(session).list_versions(actor=actor, document_id=document_id)
    return [
        DocumentVersionResponse.model_validate(version, from_attributes=True)
        for version in versions
    ]


@document_router.post(
    "/{document_id}/versions",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_version(
    document_id: UUID,
    payload: DocumentVersionUploadRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> DocumentResponse:
    document = DocumentService(session).create_version(
        actor=actor,
        document_id=document_id,
        payload=payload,
    )
    return DocumentResponse.model_validate(document, from_attributes=True)


@document_router.get("/{document_id}/jobs", response_model=list[ProcessingJobResponse])
async def list_document_jobs(
    document_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[ProcessingJobResponse]:
    jobs = DocumentService(session).list_jobs(actor=actor, document_id=document_id)
    return [ProcessingJobResponse.model_validate(job, from_attributes=True) for job in jobs]
