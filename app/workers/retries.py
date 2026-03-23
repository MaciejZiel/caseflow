"""Retry worker entrypoints for due jobs, digests and outbound deliveries."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.application.services.documents import DocumentService
from app.application.services.emails import EmailOutboxService
from app.application.services.webhooks import WebhookService
from app.core.config import get_settings
from app.infrastructure.db.session import get_session_factory


@dataclass(slots=True)
class RetryCycleResult:
    processed_document_jobs: int
    processed_webhook_deliveries: int
    processed_admin_notification_digests: int
    processed_emails: int


def run_retry_cycle(*, limit_per_queue: int = 50) -> RetryCycleResult:
    session = get_session_factory()()
    try:
        processed_document_jobs = len(
            DocumentService(session).process_due_jobs(limit=limit_per_queue)
        )
        processed_webhook_deliveries = len(
            WebhookService(session).process_due_deliveries(limit=limit_per_queue)
        )
        from app.application.services.admin_notifications import AdminNotificationService

        processed_admin_notification_digests = AdminNotificationService(
            session
        ).process_due_digests(limit=limit_per_queue)
        processed_emails = len(
            EmailOutboxService(session).process_due_emails(limit=limit_per_queue)
        )
        return RetryCycleResult(
            processed_document_jobs=processed_document_jobs,
            processed_webhook_deliveries=processed_webhook_deliveries,
            processed_admin_notification_digests=processed_admin_notification_digests,
            processed_emails=processed_emails,
        )
    finally:
        session.close()


def run_retry_worker(
    *,
    limit_per_queue: int = 50,
    poll_interval_seconds: int | None = None,
) -> None:
    settings = get_settings()
    poll_interval = poll_interval_seconds or settings.worker_poll_interval_seconds
    while True:
        run_retry_cycle(limit_per_queue=limit_per_queue)
        time.sleep(poll_interval)
