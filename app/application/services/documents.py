"""Document upload, versioning and job orchestration services."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.documents import (
    DocumentApproveRequest,
    DocumentRejectRequest,
    DocumentUploadRequest,
    DocumentVersionUploadRequest,
)
from app.application.actors import ActorContext
from app.application.services.events import EventPublisher
from app.application.services.webhooks import WebhookService
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
    DOCUMENT_RETRY_ROLES,
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
        self.publisher = EventPublisher(session)

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
        previous_case_status = case.status
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
            actor_user_id=actor.user.id,
            event_type="document.uploaded",
            metadata={
                "document_version_id": version.id,
                "job_id": job.id,
                "version_number": version.version_number,
            },
            case=case,
            previous_case_status=previous_case_status,
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

    def list_case_documents(self, *, actor: ActorContext, case_id: UUID) -> list[Document]:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=DOCUMENT_READ_ROLES,
            message="Your role cannot view documents.",
        )
        case = self._get_case_for_actor(actor=actor, case_id=case_id)
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        return list(
            self.session.scalars(
                select(Document)
                .where(
                    Document.case_id == case_id,
                    Document.organization_id == actor.organization.id,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.created_at.desc(), Document.updated_at.desc())
            )
        )

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
        previous_case_status = case.status
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
            actor_user_id=actor.user.id,
            event_type="document.version_uploaded",
            metadata={
                "document_version_id": version.id,
                "job_id": job.id,
                "version_number": version.version_number,
            },
            case=case,
            previous_case_status=previous_case_status,
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

    def process_due_jobs(
        self,
        *,
        limit: int = 50,
        organization_id: UUID | None = None,
    ) -> list[UUID]:
        now = datetime.now(UTC)
        query = select(ProcessingJob.id).where(
            or_(
                and_(
                    ProcessingJob.status == ProcessingJobStatus.QUEUED,
                    ProcessingJob.scheduled_at <= now,
                ),
                and_(
                    ProcessingJob.status == ProcessingJobStatus.FAILED,
                    ProcessingJob.next_retry_at.is_not(None),
                    ProcessingJob.next_retry_at <= now,
                ),
            )
        )
        if organization_id is not None:
            query = query.where(ProcessingJob.organization_id == organization_id)
        job_ids = list(
            self.session.scalars(
                query.order_by(
                    func.coalesce(
                        ProcessingJob.next_retry_at,
                        ProcessingJob.scheduled_at,
                        ProcessingJob.created_at,
                    ).asc()
                ).limit(limit)
            )
        )
        for job_id in job_ids:
            self.process_document_job(job_id=job_id)
        return job_ids

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
        job = self.session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id))
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

        previous_case_status = case.status
        job.attempts += 1
        job.status = ProcessingJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.finished_at = None
        job.last_error = None
        document.status = DocumentStatus.PROCESSING
        version.processing_status = DocumentProcessingStatus.PROCESSING
        job.next_retry_at = None
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
                previous_case_status=previous_case_status,
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
        job.next_retry_at = None
        case.status = CaseStatus.IN_REVIEW
        delivery_ids = self.publisher.record_event(
            organization_id=document.organization_id,
            actor_user_id=None,
            event_type="document.processing_succeeded",
            entity_type="document",
            entity_id=document.id,
            new_values=self._document_snapshot(document),
            metadata={
                "document_version_id": version.id,
                "job_id": job.id,
                "processing_status": version.processing_status,
            },
        )
        delivery_ids.extend(
            self._record_case_status_change_if_needed(
                case=case,
                previous_status=previous_case_status,
                actor_user_id=None,
                metadata={"document_id": document.id, "job_id": job.id},
            )
        )
        self.session.commit()
        WebhookService(self.session).dispatch_enqueued_deliveries(delivery_ids)

    def retry_job(
        self,
        *,
        actor: ActorContext,
        document_id: UUID,
        job_id: UUID,
    ) -> ProcessingJob:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=DOCUMENT_RETRY_ROLES,
            message="Your role cannot retry document processing jobs.",
        )
        self.get_document(actor=actor, document_id=document_id)
        job = self.session.scalar(
            select(ProcessingJob).where(
                ProcessingJob.id == job_id,
                ProcessingJob.document_id == document_id,
                ProcessingJob.organization_id == actor.organization.id,
            )
        )
        if job is None:
            raise NotFoundError("processing_job", "Processing job does not exist.")
        if job.status not in {ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTERED}:
            raise DomainValidationError(
                "processing_job_retry_forbidden",
                "Only failed or dead-lettered jobs can be retried.",
            )

        document = self._get_document_for_actor(actor=actor, document_id=document_id)
        version = self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == job.document_version_id,
                DocumentVersion.organization_id == actor.organization.id,
            )
        )
        if document is None or version is None:
            raise NotFoundError("document", "Document does not exist.")

        self._reset_job_for_retry(
            job=job,
            document=document,
            version=version,
            scheduled_at=datetime.now(UTC),
        )
        self.session.commit()

        self.process_document_job(job_id=job.id)
        self.session.refresh(job)
        return job

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
        actor_user_id: UUID,
        event_type: str,
        metadata: dict[str, object],
        case: Case,
        previous_case_status: CaseStatus,
    ) -> None:
        self.storage.save_file(storage_key=version.storage_key, content=content)
        try:
            self.session.add(document)
            self.session.add(version)
            self.session.add(job)
            self.session.flush()
            delivery_ids = self.publisher.record_event(
                organization_id=document.organization_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                entity_type="document",
                entity_id=document.id,
                new_values=self._document_snapshot(document),
                metadata=metadata,
            )
            delivery_ids.extend(
                self._record_case_status_change_if_needed(
                    case=case,
                    previous_status=previous_case_status,
                    actor_user_id=actor_user_id,
                    metadata={"document_id": document.id},
                )
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.storage.delete_file(storage_key=version.storage_key)
            raise

        self.session.refresh(document)
        WebhookService(self.session).dispatch_enqueued_deliveries(delivery_ids)

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
        previous_document_status = document.status
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
        previous_case_status = case.status
        case.status = self._calculate_case_status_after_review(
            case=case,
            current_document=document,
        )
        delivery_ids = self.publisher.record_event(
            organization_id=actor.organization.id,
            actor_user_id=actor.user.id,
            event_type=(
                "document.approved"
                if decision == DocumentReviewDecision.APPROVED
                else "document.rejected"
            ),
            entity_type="document",
            entity_id=document.id,
            old_values={"status": previous_document_status},
            new_values=self._document_snapshot(document),
            metadata={"reason": review.reason},
        )
        delivery_ids.extend(
            self._record_case_status_change_if_needed(
                case=case,
                previous_status=previous_case_status,
                actor_user_id=actor.user.id,
                metadata={"document_id": document.id, "decision": decision},
            )
        )

        self.session.commit()
        self.session.refresh(document)
        WebhookService(self.session).dispatch_enqueued_deliveries(delivery_ids)
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
        previous_case_status: CaseStatus,
        error: Exception,
    ) -> None:
        job.last_error = str(error)
        job.finished_at = datetime.now(UTC)
        job.status = (
            ProcessingJobStatus.DEAD_LETTERED
            if job.attempts >= job.max_attempts
            else ProcessingJobStatus.FAILED
        )
        job.next_retry_at = (
            None
            if job.status == ProcessingJobStatus.DEAD_LETTERED
            else datetime.now(UTC)
            + timedelta(
                seconds=self.settings.job_retry_base_delay_seconds * (2 ** max(job.attempts - 1, 0))
            )
        )
        document.status = DocumentStatus.FAILED
        version.processing_status = DocumentProcessingStatus.FAILED
        case.status = CaseStatus.WAITING_FOR_DOCUMENTS
        delivery_ids = self.publisher.record_event(
            organization_id=document.organization_id,
            actor_user_id=None,
            event_type="document.processing_failed",
            entity_type="document",
            entity_id=document.id,
            new_values=self._document_snapshot(document),
            metadata={
                "document_version_id": version.id,
                "job_id": job.id,
                "last_error": job.last_error,
            },
        )
        delivery_ids.extend(
            self._record_case_status_change_if_needed(
                case=case,
                previous_status=previous_case_status,
                actor_user_id=None,
                metadata={"document_id": document.id, "job_id": job.id},
            )
        )
        self.session.commit()
        WebhookService(self.session).dispatch_enqueued_deliveries(delivery_ids)

    def _reset_job_for_retry(
        self,
        *,
        job: ProcessingJob,
        document: Document,
        version: DocumentVersion,
        scheduled_at: datetime,
    ) -> None:
        document.status = DocumentStatus.QUEUED
        version.processing_status = DocumentProcessingStatus.QUEUED
        job.status = ProcessingJobStatus.QUEUED
        job.last_error = None
        job.started_at = None
        job.finished_at = None
        job.scheduled_at = scheduled_at
        job.next_retry_at = None

    def _extract_payload(
        self,
        *,
        content: bytes,
        version: DocumentVersion,
    ) -> dict[str, object]:
        if content.startswith(b"FAIL_PROCESSING"):
            raise DomainValidationError(
                "document_processing_simulated_failure",
                "Document processing failed because the payload was marked as invalid.",
            )
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

    def _record_case_status_change_if_needed(
        self,
        *,
        case: Case,
        previous_status: CaseStatus,
        actor_user_id: UUID | None,
        metadata: dict[str, object] | None = None,
    ) -> list[UUID]:
        if case.status == previous_status:
            return []
        return self.publisher.record_event(
            organization_id=case.organization_id,
            actor_user_id=actor_user_id,
            event_type="case.status_changed",
            entity_type="case",
            entity_id=case.id,
            old_values={"status": previous_status},
            new_values={"status": case.status},
            metadata=metadata,
        )

    @staticmethod
    def _document_snapshot(document: Document) -> dict[str, object]:
        return {
            "id": document.id,
            "case_id": document.case_id,
            "current_version_id": document.current_version_id,
            "document_type": document.document_type,
            "title": document.title,
            "status": document.status,
            "uploaded_by": document.uploaded_by,
            "checksum": document.checksum,
            "mime_type": document.mime_type,
            "size_bytes": document.size_bytes,
            "storage_key": document.storage_key,
            "deleted_at": document.deleted_at,
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
