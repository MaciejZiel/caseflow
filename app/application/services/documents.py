"""Document upload, versioning and job orchestration services."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.documents import DocumentUploadRequest, DocumentVersionUploadRequest
from app.application.actors import ActorContext
from app.core.config import get_settings
from app.core.errors import DomainValidationError, NotFoundError
from app.domain.cases.models import Case
from app.domain.documents.models import (
    Document,
    DocumentProcessingStatus,
    DocumentStatus,
    DocumentVersion,
)
from app.domain.documents.policies import DOCUMENT_READ_ROLES, DOCUMENT_WRITE_ROLES
from app.domain.jobs.models import ProcessingJob, ProcessingJobStatus, ProcessingJobType
from app.domain.organizations.policies import ensure_role_allowed
from app.infrastructure.storage.local import LocalFileStorage

ALLOWED_DOCUMENT_MIME_TYPES = frozenset(
    {
        "application/json",
        "application/octet-stream",
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
    }
)


@dataclass(slots=True)
class PreparedUpload:
    content: bytes
    mime_type: str
    original_filename: str
    size_bytes: int


class DocumentService:
    def __init__(
        self,
        session: Session,
        *,
        storage: LocalFileStorage | None = None,
    ) -> None:
        self.session = session
        self.storage = storage or LocalFileStorage()
        self.settings = get_settings()

    def create_document(
        self,
        *,
        actor: ActorContext,
        case_id: UUID,
        payload: DocumentUploadRequest,
    ) -> Document:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=DOCUMENT_WRITE_ROLES,
            message="Your role cannot upload documents.",
        )
        case = self._get_case_for_actor(actor=actor, case_id=case_id)
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        if case.archived_at is not None:
            raise DomainValidationError(
                "archived_case_document_upload_forbidden",
                "Cannot upload documents to an archived case.",
            )

        prepared_upload = self._prepare_upload(
            mime_type=payload.mime_type,
            original_filename=payload.original_filename,
            content_base64=payload.content_base64,
        )
        document_id = uuid4()
        version_id = uuid4()
        storage_key = self._build_storage_key(
            organization_id=actor.organization.id,
            case_id=case.id,
            document_id=document_id,
            version_number=1,
            original_filename=prepared_upload.original_filename,
        )

        document = Document(
            id=document_id,
            organization_id=actor.organization.id,
            case_id=case.id,
            current_version_id=version_id,
            document_type=payload.document_type,
            title=payload.title,
            status=DocumentStatus.QUEUED,
            uploaded_by=actor.user.id,
            checksum=None,
            mime_type=prepared_upload.mime_type,
            size_bytes=prepared_upload.size_bytes,
            storage_key=storage_key,
        )
        version = DocumentVersion(
            id=version_id,
            organization_id=actor.organization.id,
            document_id=document.id,
            version_number=1,
            original_filename=prepared_upload.original_filename,
            storage_key=storage_key,
            checksum=None,
            mime_type=prepared_upload.mime_type,
            size_bytes=prepared_upload.size_bytes,
            uploaded_by=actor.user.id,
            processing_status=DocumentProcessingStatus.QUEUED,
        )
        job = self._build_processing_job(
            actor=actor,
            document=document,
            version=version,
            event_name="document.uploaded",
        )
        self._save_document_bundle(
            document=document,
            version=version,
            job=job,
            content=prepared_upload.content,
        )
        return document

    def get_document(self, *, actor: ActorContext, document_id: UUID) -> Document:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=DOCUMENT_READ_ROLES,
            message="Your role cannot view documents.",
        )
        document = self._get_document_for_actor(actor=actor, document_id=document_id)
        if document is None:
            raise NotFoundError("document", "Document does not exist.")
        return document

    def list_versions(self, *, actor: ActorContext, document_id: UUID) -> list[DocumentVersion]:
        self.get_document(actor=actor, document_id=document_id)
        return list(
            self.session.scalars(
                select(DocumentVersion)
                .where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.organization_id == actor.organization.id,
                )
                .order_by(DocumentVersion.version_number.asc())
            )
        )

    def create_version(
        self,
        *,
        actor: ActorContext,
        document_id: UUID,
        payload: DocumentVersionUploadRequest,
    ) -> Document:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=DOCUMENT_WRITE_ROLES,
            message="Your role cannot upload document versions.",
        )
        document = self._get_document_for_actor(actor=actor, document_id=document_id)
        if document is None:
            raise NotFoundError("document", "Document does not exist.")
        case = self._get_case_for_actor(actor=actor, case_id=document.case_id)
        if case is None or case.archived_at is not None:
            raise DomainValidationError(
                "document_version_upload_forbidden",
                "Cannot upload a new version for a document in an archived or missing case.",
            )

        prepared_upload = self._prepare_upload(
            mime_type=payload.mime_type,
            original_filename=payload.original_filename,
            content_base64=payload.content_base64,
        )
        next_version_number = self._get_next_version_number(document_id=document.id)
        version_id = uuid4()
        storage_key = self._build_storage_key(
            organization_id=actor.organization.id,
            case_id=document.case_id,
            document_id=document.id,
            version_number=next_version_number,
            original_filename=prepared_upload.original_filename,
        )

        if payload.title is not None:
            document.title = payload.title
        if payload.document_type is not None:
            document.document_type = payload.document_type
        document.current_version_id = version_id
        document.status = DocumentStatus.QUEUED
        document.checksum = None
        document.mime_type = prepared_upload.mime_type
        document.size_bytes = prepared_upload.size_bytes
        document.storage_key = storage_key

        version = DocumentVersion(
            id=version_id,
            organization_id=actor.organization.id,
            document_id=document.id,
            version_number=next_version_number,
            original_filename=prepared_upload.original_filename,
            storage_key=storage_key,
            checksum=None,
            mime_type=prepared_upload.mime_type,
            size_bytes=prepared_upload.size_bytes,
            uploaded_by=actor.user.id,
            processing_status=DocumentProcessingStatus.QUEUED,
        )
        job = self._build_processing_job(
            actor=actor,
            document=document,
            version=version,
            event_name="document.version_uploaded",
        )
        self._save_document_bundle(
            document=document,
            version=version,
            job=job,
            content=prepared_upload.content,
        )
        return document

    def list_jobs(self, *, actor: ActorContext, document_id: UUID) -> list[ProcessingJob]:
        self.get_document(actor=actor, document_id=document_id)
        return list(
            self.session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.document_id == document_id,
                    ProcessingJob.organization_id == actor.organization.id,
                )
                .order_by(ProcessingJob.created_at.desc())
            )
        )

    def _build_processing_job(
        self,
        *,
        actor: ActorContext,
        document: Document,
        version: DocumentVersion,
        event_name: str,
    ) -> ProcessingJob:
        return ProcessingJob(
            organization_id=actor.organization.id,
            document_id=document.id,
            document_version_id=version.id,
            job_type=ProcessingJobType.DOCUMENT_PROCESSING,
            status=ProcessingJobStatus.QUEUED,
            payload_json={
                "case_id": str(document.case_id),
                "document_id": str(document.id),
                "document_version_id": str(version.id),
                "event_name": event_name,
            },
        )

    def _save_document_bundle(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        job: ProcessingJob,
        content: bytes,
    ) -> None:
        self.storage.save_file(storage_key=version.storage_key, content=content)
        try:
            self.session.add(document)
            self.session.add(version)
            self.session.add(job)
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.storage.delete_file(storage_key=version.storage_key)
            raise

        self.session.refresh(document)

    def _prepare_upload(
        self,
        *,
        mime_type: str,
        original_filename: str,
        content_base64: str,
    ) -> PreparedUpload:
        if mime_type not in ALLOWED_DOCUMENT_MIME_TYPES:
            raise DomainValidationError(
                "unsupported_document_mime_type",
                "This MIME type is not allowed for document uploads.",
            )

        try:
            content = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise DomainValidationError(
                "invalid_document_content",
                "Document content must be valid base64-encoded data.",
            ) from exc

        if not content:
            raise DomainValidationError(
                "empty_document_upload",
                "Document content cannot be empty.",
            )
        if len(content) > self.settings.max_upload_size_bytes:
            raise DomainValidationError(
                "document_too_large",
                "Document exceeds the configured upload size limit.",
            )

        return PreparedUpload(
            content=content,
            mime_type=mime_type,
            original_filename=LocalFileStorage.sanitize_filename(original_filename),
            size_bytes=len(content),
        )

    def _get_case_for_actor(self, *, actor: ActorContext, case_id: UUID) -> Case | None:
        return self.session.scalar(
            select(Case).where(
                Case.id == case_id,
                Case.organization_id == actor.organization.id,
            )
        )

    def _get_document_for_actor(self, *, actor: ActorContext, document_id: UUID) -> Document | None:
        return self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == actor.organization.id,
            )
        )

    def _get_next_version_number(self, *, document_id: UUID) -> int:
        current_max = self.session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document_id,
            )
        )
        return int(current_max or 0) + 1

    def _build_storage_key(
        self,
        *,
        organization_id: UUID,
        case_id: UUID,
        document_id: UUID,
        version_number: int,
        original_filename: str,
    ) -> str:
        return (
            f"{organization_id}/cases/{case_id}/documents/{document_id}/"
            f"v{version_number}/{original_filename}"
        )
