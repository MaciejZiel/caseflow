"""Schemas for document upload, versioning and job inspection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.documents.models import DocumentProcessingStatus, DocumentStatus, DocumentType
from app.domain.jobs.models import ProcessingJobStatus, ProcessingJobType


class DocumentUploadRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    document_type: DocumentType = DocumentType.OTHER
    original_filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=255)
    content_base64: str = Field(min_length=4, max_length=15_000_000)

    @field_validator("mime_type")
    @classmethod
    def normalize_mime_type(cls, value: str) -> str:
        return value.strip().lower()


class DocumentVersionUploadRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    document_type: DocumentType | None = None
    original_filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=3, max_length=255)
    content_base64: str = Field(min_length=4, max_length=15_000_000)

    @field_validator("mime_type")
    @classmethod
    def normalize_mime_type(cls, value: str) -> str:
        return value.strip().lower()


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    current_version_id: UUID | None
    document_type: DocumentType
    title: str
    status: DocumentStatus
    uploaded_by: UUID
    checksum: str | None
    mime_type: str | None
    size_bytes: int | None
    storage_key: str | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    version_number: int
    original_filename: str
    storage_key: str
    checksum: str | None
    mime_type: str
    size_bytes: int
    uploaded_by: UUID
    processing_status: DocumentProcessingStatus
    extracted_payload_json: dict[str, object] | None
    created_at: datetime


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_version_id: UUID
    job_type: ProcessingJobType
    status: ProcessingJobStatus
    attempts: int
    max_attempts: int
    last_error: str | None
    payload_json: dict[str, object]
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
