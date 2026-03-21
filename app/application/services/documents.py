"""Document upload, versioning and job orchestration services."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.documents import (
    DocumentApproveRequest,
    DocumentRejectRequest,
    DocumentUploadRequest,
    DocumentVersionUploadRequest,
)
from app.application.actors import ActorContext
from app.core.config import get_settings
from app.core.errors import DomainValidationError, NotFoundError
from app.domain.cases.models import Case, CaseStatus
from app.domain.documents.models import (
    Document,
    DocumentProcessingStatus,
    DocumentReview,
    DocumentReviewDecision,
    DocumentStatus,
    DocumentVersion,
)
from app.domain.documents.policies import (
    DOCUMENT_READ_ROLES,
    DOCUMENT_REVIEW_ROLES,
    DOCUMENT_WRITE_ROLES,
)
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


@dataclass(slots=True)
class DocumentWriteResult:
    document: Document
    job: ProcessingJob


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
    ) -> DocumentWriteResult:
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
        case.status = CaseStatus.IN_REVIEW

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
        return DocumentWriteResult(document=document, job=job)

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
    ) -> DocumentWriteResult:
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
        case.status = CaseStatus.IN_REVIEW

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
        return DocumentWriteResult(document=document, job=job)

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

    def approve_document(
        self,
        *,
        actor: ActorContext,
        document_id: UUID,
        payload: DocumentApproveRequest,
    ) -> Document:
        return self._review_document(
            actor=actor,
            document_id=document_id,
            decision=DocumentReviewDecision.APPROVED,
            reason=payload.reason,
        )

    def reject_document(
        self,
        *,
        actor: ActorContext,
        document_id: UUID,
        payload: DocumentRejectRequest,
    ) -> Document:
        return self._review_document(
            actor=actor,
            document_id=document_id,
            decision=DocumentReviewDecision.REJECTED,
            reason=payload.reason,
        )

    def process_document_job(self, *, job_id: UUID) -> None:
        job = self.session.scalar(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )
        if job is None:
            return
        if job.status not in {ProcessingJobStatus.QUEUED, ProcessingJobStatus.FAILED}:
            return

        document = self.session.scalar(
            select(Document).where(
                Document.id == job.document_id,
                Document.organization_id == job.organization_id,
            )
        )
        version = self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == job.document_version_id,
                DocumentVersion.organization_id == job.organization_id,
            )
        )
        case = self.session.scalar(
            select(Case).where(
                Case.id == UUID(str(job.payload_json["case_id"])),
                Case.organization_id == job.organization_id,
            )
        )
        if document is None or version is None or case is None:
            return

        job.attempts += 1
        job.status = ProcessingJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.finished_at = None
        job.last_error = None
        document.status = DocumentStatus.PROCESSING
        version.processing_status = DocumentProcessingStatus.PROCESSING
        self.session.commit()

        try:
            file_content = self.storage.read_file(storage_key=version.storage_key)
            checksum = sha256(file_content).hexdigest()
            extracted_payload = self._extract_payload(
                content=file_content,
                version=version,
            )
        except Exception as exc:
            self.session.rollback()
            self._mark_processing_failed(
                job=job,
                document=document,
                version=version,
                case=case,
                error=exc,
            )
            return

        document.status = DocumentStatus.READY
        document.checksum = checksum
        document.mime_type = version.mime_type
        document.size_bytes = version.size_bytes
        document.storage_key = version.storage_key
        version.processing_status = DocumentProcessingStatus.READY
        version.checksum = checksum
        version.extracted_payload_json = extracted_payload
        job.status = ProcessingJobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC)
        case.status = CaseStatus.IN_REVIEW
        self.session.commit()

    def _build_processing_job(
        self,
        *,
        actor: ActorContext,
        document: Document,
        version: DocumentVersion,
        event_name: str,
    ) -> ProcessingJob:
        return ProcessingJob(
            id=uuid4(),
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
                "storage_key": version.storage_key,
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

    def _review_document(
        self,
        *,
        actor: ActorContext,
        document_id: UUID,
        decision: DocumentReviewDecision,
        reason: str | None,
    ) -> Document:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=DOCUMENT_REVIEW_ROLES,
            message="Your role cannot review documents.",
        )
        document = self._get_document_for_actor(actor=actor, document_id=document_id)
        if document is None:
            raise NotFoundError("document", "Document does not exist.")
        if document.status != DocumentStatus.READY:
            raise DomainValidationError(
                "document_review_forbidden",
                "Only ready documents can be approved or rejected.",
            )

        review = DocumentReview(
            organization_id=actor.organization.id,
            document_id=document.id,
            reviewer_user_id=actor.user.id,
            decision=decision,
            reason=reason.strip() if reason is not None else None,
        )
        document.status = (
            DocumentStatus.APPROVED
            if decision == DocumentReviewDecision.APPROVED
            else DocumentStatus.REJECTED
        )
        self.session.add(review)
        self.session.flush()
        case = self._get_case_for_actor(actor=actor, case_id=document.case_id)
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        case.status = self._calculate_case_status_after_review(
            case=case,
            current_document=document,
        )

        self.session.commit()
        self.session.refresh(document)
        return document

    def _calculate_case_status_after_review(
        self,
        *,
        case: Case,
        current_document: Document,
    ) -> CaseStatus:
        if current_document.status == DocumentStatus.REJECTED:
            return CaseStatus.REJECTED

        document_statuses = list(
            self.session.scalars(
                select(Document.status).where(
                    Document.case_id == case.id,
                    Document.organization_id == case.organization_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        if document_statuses and all(
            status == DocumentStatus.APPROVED for status in document_statuses
        ):
            return CaseStatus.APPROVED
        return CaseStatus.IN_REVIEW

    def _mark_processing_failed(
        self,
        *,
        job: ProcessingJob,
        document: Document,
        version: DocumentVersion,
        case: Case,
        error: Exception,
    ) -> None:
        job.last_error = str(error)
        job.finished_at = datetime.now(UTC)
        job.status = (
            ProcessingJobStatus.DEAD_LETTERED
            if job.attempts >= job.max_attempts
            else ProcessingJobStatus.FAILED
        )
        document.status = DocumentStatus.FAILED
        version.processing_status = DocumentProcessingStatus.FAILED
        case.status = CaseStatus.WAITING_FOR_DOCUMENTS
        self.session.commit()

    def _extract_payload(
        self,
        *,
        content: bytes,
        version: DocumentVersion,
    ) -> dict[str, object]:
        preview_text = content[:200].decode("utf-8", errors="replace").strip()
        preview_lines = [line for line in preview_text.splitlines() if line]
        return {
            "checksum_sha256": sha256(content).hexdigest(),
            "line_count": len(content.decode("utf-8", errors="replace").splitlines()),
            "mime_type": version.mime_type,
            "original_filename": version.original_filename,
            "preview_text": preview_lines[0] if preview_lines else preview_text[:120],
            "size_bytes": version.size_bytes,
            "storage_url": self.storage.build_public_or_signed_url(storage_key=version.storage_key),
        }

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
