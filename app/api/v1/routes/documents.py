"""Document upload, versioning and job inspection routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.audit import AuditLogResponse
from app.api.v1.schemas.documents import (
    DocumentApproveRequest,
    DocumentRejectRequest,
    DocumentResponse,
    DocumentUploadRequest,
    DocumentVersionResponse,
    DocumentVersionUploadRequest,
    ProcessingJobResponse,
)
from app.application.services.audit import AuditService
from app.application.services.documents import DocumentService
from app.core.config import get_settings
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
    service = DocumentService(session)
    result = service.create_document(
        actor=actor,
        case_id=case_id,
        payload=payload,
    )
    response = DocumentResponse.model_validate(result.document, from_attributes=True)
    if get_settings().document_processing_mode == "inline":
        service.process_document_job(job_id=result.job.id)
    return response


@case_router.get("/{case_id}/documents", response_model=list[DocumentResponse])
async def list_case_documents(
    case_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[DocumentResponse]:
    documents = DocumentService(session).list_case_documents(actor=actor, case_id=case_id)
    return [DocumentResponse.model_validate(document, from_attributes=True) for document in documents]


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
    service = DocumentService(session)
    result = service.create_version(
        actor=actor,
        document_id=document_id,
        payload=payload,
    )
    response = DocumentResponse.model_validate(result.document, from_attributes=True)
    if get_settings().document_processing_mode == "inline":
        service.process_document_job(job_id=result.job.id)
    return response


@document_router.get("/{document_id}/jobs", response_model=list[ProcessingJobResponse])
async def list_document_jobs(
    document_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[ProcessingJobResponse]:
    jobs = DocumentService(session).list_jobs(actor=actor, document_id=document_id)
    return [ProcessingJobResponse.model_validate(job, from_attributes=True) for job in jobs]


@document_router.post(
    "/{document_id}/jobs/{job_id}/retry",
    response_model=ProcessingJobResponse,
)
async def retry_document_job(
    document_id: UUID,
    job_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> ProcessingJobResponse:
    job = DocumentService(session).retry_job(
        actor=actor,
        document_id=document_id,
        job_id=job_id,
    )
    return ProcessingJobResponse.model_validate(job, from_attributes=True)


@document_router.get("/{document_id}/audit-log", response_model=list[AuditLogResponse])
async def list_document_audit_log(
    document_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[AuditLogResponse]:
    DocumentService(session).get_document(actor=actor, document_id=document_id)
    logs = AuditService(session).list_entity_logs(
        organization_id=actor.organization.id,
        entity_type="document",
        entity_id=document_id,
    )
    return [AuditLogResponse.model_validate(log, from_attributes=True) for log in logs]


@document_router.post("/{document_id}/approve", response_model=DocumentResponse)
async def approve_document(
    document_id: UUID,
    payload: DocumentApproveRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> DocumentResponse:
    document = DocumentService(session).approve_document(
        actor=actor,
        document_id=document_id,
        payload=payload,
    )
    return DocumentResponse.model_validate(document, from_attributes=True)


@document_router.post("/{document_id}/reject", response_model=DocumentResponse)
async def reject_document(
    document_id: UUID,
    payload: DocumentRejectRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> DocumentResponse:
    document = DocumentService(session).reject_document(
        actor=actor,
        document_id=document_id,
        payload=payload,
    )
    return DocumentResponse.model_validate(document, from_attributes=True)
