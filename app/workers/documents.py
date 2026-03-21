"""In-process document processing worker tasks."""

from __future__ import annotations

from uuid import UUID

from app.application.services.documents import DocumentService
from app.infrastructure.db.session import get_session_factory


def process_document_job(job_id: UUID) -> None:
    session = get_session_factory()()
    try:
        DocumentService(session).process_document_job(job_id=job_id)
    finally:
        session.close()
