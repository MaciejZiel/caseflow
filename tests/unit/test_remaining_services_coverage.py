from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.v1.schemas.admin_notifications import AdminNotificationPreferenceUpdateRequest
from app.api.v1.schemas.admin_reviews import AdminReviewAutoAssignRequest
from app.api.v1.schemas.documents import DocumentUploadRequest, DocumentVersionUploadRequest
from app.application.services import admin_notifications as admin_notifications_service
from app.application.services import admin_reviews as admin_reviews_service
from app.application.services import assistant as assistant_service
from app.application.services import cases as cases_service
from app.application.services import documents as documents_service
from app.application.services import emails as emails_service
from app.application.services import invitations as invitations_service
from app.application.services import operations as operations_service
from app.application.services import reporting as reporting_service
from app.core.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.domain.admin_notifications.models import (
    AdminNotificationDigestSchedule,
    AdminNotificationType,
)
from app.domain.admin_reviews.models import AdminReviewPriority, AdminReviewStatus
from app.domain.cases.models import CaseStatus
from app.domain.documents.models import DocumentStatus, DocumentType
from app.domain.jobs.models import ProcessingJobStatus
from app.domain.organizations.models import OrganizationRole, OrganizationStatus
from tests.unit.test_auth_webhooks_and_admin_branches import SessionRecorder


def build_actor(
    *,
    role: OrganizationRole = OrganizationRole.OWNER,
    is_superuser: bool = False,
) -> SimpleNamespace:
    organization = SimpleNamespace(id=uuid4(), status=OrganizationStatus.ACTIVE)
    user = SimpleNamespace(
        id=uuid4(),
        email="actor@example.com",
        first_name="Case",
        last_name="Flow",
        is_superuser=is_superuser,
        is_active=True,
    )
    membership = SimpleNamespace(
        id=uuid4(),
        role=role,
        organization=organization,
        is_active=True,
    )
    return SimpleNamespace(user=user, membership=membership, organization=organization)


def encode_payload(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def test_assistant_case_guards_and_tokenless_snippets_cover_remaining_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = build_actor()
    service = assistant_service.AssistantService(SessionRecorder())
    monkeypatch.setattr(assistant_service, "ensure_role_allowed", lambda *_args, **_kwargs: None)

    with pytest.raises(NotFoundError):
        service._get_case(actor=actor, case_id=uuid4())

    session = SessionRecorder(scalars_values=[[]])
    service = assistant_service.AssistantService(session)
    monkeypatch.setattr(service, "_get_case", lambda **_kwargs: SimpleNamespace(id=uuid4()))
    assert service.list_conversations(actor=actor, case_id=uuid4()) == []

    failed_document = SimpleNamespace(
        id=uuid4(),
        title="Broken invoice",
        document_type=DocumentType.INVOICE,
        status=DocumentStatus.FAILED,
        current_version_id=None,
        updated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    session = SessionRecorder(scalars_values=[[failed_document], []], scalar_values=[""])
    service = assistant_service.AssistantService(session)
    snippets = service._collect_document_snippets(
        case=SimpleNamespace(id=uuid4(), organization_id=actor.organization.id),
        question="???",
    )

    assert len(snippets) == 1
    assert snippets[0].score == 2


def test_case_service_conflict_and_unexpected_field_branches_are_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = build_actor()
    monkeypatch.setattr(cases_service, "ensure_role_allowed", lambda *_args, **_kwargs: None)

    create_session = SessionRecorder(flush_error=IntegrityError("insert", {}, RuntimeError("boom")))
    service = cases_service.CaseService(create_session)
    service.publisher = SimpleNamespace(record_event=lambda **_kwargs: [uuid4()])
    monkeypatch.setattr(service, "_validate_case_owner", lambda **_kwargs: None)

    with pytest.raises(ConflictError) as create_conflict:
        service.create_case(
            actor=actor,
            payload=SimpleNamespace(
                external_id="CASE-1",
                title="Create conflict",
                description=None,
                priority="normal",
                owner_user_id=None,
                due_date=None,
            ),
        )
    assert create_conflict.value.code == "case_external_id_conflict"
    assert create_session.rollbacks == 1

    case = SimpleNamespace(
        id=uuid4(),
        organization_id=actor.organization.id,
        external_id="CASE-2",
        title="Update conflict",
        description=None,
        status=CaseStatus.NEW,
        priority="normal",
        owner_user_id=None,
        created_by=actor.user.id,
        due_date=None,
        archived_at=None,
    )
    payload = SimpleNamespace(
        model_fields_set={"status", "unexpected"},
        status=CaseStatus.IN_REVIEW,
    )
    payload.unexpected = "ignored"
    update_session = SessionRecorder(flush_error=IntegrityError("update", {}, RuntimeError("boom")))
    service = cases_service.CaseService(update_session)
    service.publisher = SimpleNamespace(record_event=lambda **_kwargs: [uuid4()])
    monkeypatch.setattr(service, "_get_case_for_actor", lambda **_kwargs: case)

    with pytest.raises(ConflictError) as update_conflict:
        service.update_case(actor=actor, case_id=case.id, payload=payload)
    assert update_conflict.value.code == "case_external_id_conflict"
    assert case.status == CaseStatus.IN_REVIEW


def test_invitation_service_conflict_and_time_conversion_branches_are_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = build_actor()
    invitation = SimpleNamespace(
        organization=SimpleNamespace(status=OrganizationStatus.ACTIVE),
        organization_id=actor.organization.id,
        email="invited@example.com",
        role=OrganizationRole.MEMBER,
        accepted_at=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session = SessionRecorder(
        scalar_values=[invitation, None],
        flush_error=IntegrityError("invite", {}, RuntimeError("boom")),
    )
    service = invitations_service.InvitationService(session)
    monkeypatch.setattr(
        invitations_service,
        "hash_invitation_token",
        lambda token: f"hashed:{token}",
    )
    monkeypatch.setattr(invitations_service, "hash_password", lambda _: "hashed-password")
    monkeypatch.setattr(
        invitations_service,
        "create_auth_session",
        lambda **_kwargs: (SimpleNamespace(id=uuid4()), "refresh-token"),
    )

    with pytest.raises(ConflictError) as accept_conflict:
        service.accept_invitation(
            SimpleNamespace(
                token="valid-invitation-token",
                first_name="Invited",
                last_name="User",
                password="StrongPass123",
            )
        )
    assert accept_conflict.value.code == "invitation_accept_conflict"
    assert session.rollbacks == 1

    aware = datetime.now(UTC)
    assert invitations_service._to_utc(aware) is aware


def test_document_service_guard_and_helper_branches_are_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = build_actor()
    monkeypatch.setattr(documents_service, "ensure_role_allowed", lambda *_args, **_kwargs: None)

    service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    valid_upload = DocumentUploadRequest(
        title="Upload",
        document_type="attachment",
        original_filename="upload.txt",
        mime_type="text/plain",
        content_base64=encode_payload(b"payload"),
    )
    with pytest.raises(NotFoundError):
        service.create_document(actor=actor, case_id=uuid4(), payload=valid_upload)

    archived_case = SimpleNamespace(archived_at=datetime.now(UTC))
    monkeypatch.setattr(service, "_get_case_for_actor", lambda **_kwargs: archived_case)
    with pytest.raises(DomainValidationError) as archived_upload:
        service.create_document(actor=actor, case_id=uuid4(), payload=valid_upload)
    assert archived_upload.value.code == "archived_case_document_upload_forbidden"

    service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    with pytest.raises(NotFoundError):
        service.list_case_documents(actor=actor, case_id=uuid4())

    service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    monkeypatch.setattr(service, "_get_document_for_actor", lambda **_kwargs: None)
    with pytest.raises(NotFoundError):
        service.create_version(
            actor=actor,
            document_id=uuid4(),
            payload=DocumentVersionUploadRequest(
                original_filename="v2.txt",
                mime_type="text/plain",
                content_base64=encode_payload(b"payload"),
            ),
        )

    document = SimpleNamespace(id=uuid4(), case_id=uuid4())
    service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    monkeypatch.setattr(service, "_get_document_for_actor", lambda **_kwargs: document)
    monkeypatch.setattr(service, "_get_case_for_actor", lambda **_kwargs: None)
    with pytest.raises(DomainValidationError) as version_forbidden:
        service.create_version(
            actor=actor,
            document_id=document.id,
            payload=DocumentVersionUploadRequest(
                original_filename="v2.txt",
                mime_type="text/plain",
                content_base64=encode_payload(b"payload"),
            ),
        )
    assert version_forbidden.value.code == "document_version_upload_forbidden"

    process_service = documents_service.DocumentService(
        SessionRecorder(),
        storage=SimpleNamespace(),
    )
    process_service.process_document_job(job_id=uuid4())

    queued_job = SimpleNamespace(status=ProcessingJobStatus.SUCCEEDED)
    process_service = documents_service.DocumentService(
        SessionRecorder(scalar_values=[queued_job]),
        storage=SimpleNamespace(),
    )
    process_service.process_document_job(job_id=uuid4())

    missing_bundle_job = SimpleNamespace(
        id=uuid4(),
        status=ProcessingJobStatus.QUEUED,
        document_id=uuid4(),
        document_version_id=uuid4(),
        organization_id=actor.organization.id,
        payload_json={"case_id": str(uuid4())},
    )
    process_service = documents_service.DocumentService(
        SessionRecorder(scalar_values=[missing_bundle_job, None, None, None]),
        storage=SimpleNamespace(),
    )
    process_service.process_document_job(job_id=missing_bundle_job.id)

    retry_service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    monkeypatch.setattr(
        retry_service,
        "get_document",
        lambda **_kwargs: SimpleNamespace(id=uuid4()),
    )
    with pytest.raises(NotFoundError):
        retry_service.retry_job(actor=actor, document_id=uuid4(), job_id=uuid4())

    invalid_retry_job = SimpleNamespace(status=ProcessingJobStatus.SUCCEEDED)
    retry_service = documents_service.DocumentService(
        SessionRecorder(scalar_values=[invalid_retry_job]),
        storage=SimpleNamespace(),
    )
    monkeypatch.setattr(
        retry_service,
        "get_document",
        lambda **_kwargs: SimpleNamespace(id=uuid4()),
    )
    with pytest.raises(DomainValidationError) as retry_forbidden:
        retry_service.retry_job(actor=actor, document_id=uuid4(), job_id=uuid4())
    assert retry_forbidden.value.code == "processing_job_retry_forbidden"

    failed_job = SimpleNamespace(
        id=uuid4(),
        status=ProcessingJobStatus.FAILED,
        document_version_id=uuid4(),
    )
    retry_service = documents_service.DocumentService(
        SessionRecorder(scalar_values=[failed_job, None, None]),
        storage=SimpleNamespace(),
    )
    monkeypatch.setattr(
        retry_service,
        "get_document",
        lambda **_kwargs: SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(retry_service, "_get_document_for_actor", lambda **_kwargs: None)
    with pytest.raises(NotFoundError):
        retry_service.retry_job(actor=actor, document_id=uuid4(), job_id=failed_job.id)

    helper_service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    helper_service.settings = SimpleNamespace(max_upload_size_bytes=4)
    with pytest.raises(DomainValidationError) as unsupported:
        helper_service._prepare_upload(
            mime_type="application/xml",
            original_filename="payload.xml",
            content_base64=encode_payload(b"xml"),
        )
    assert unsupported.value.code == "unsupported_document_mime_type"

    with pytest.raises(DomainValidationError) as invalid_content:
        helper_service._prepare_upload(
            mime_type="text/plain",
            original_filename="payload.txt",
            content_base64="!invalid!",
        )
    assert invalid_content.value.code == "invalid_document_content"

    with pytest.raises(DomainValidationError) as empty_upload:
        helper_service._prepare_upload(
            mime_type="text/plain",
            original_filename="payload.txt",
            content_base64=encode_payload(b""),
        )
    assert empty_upload.value.code == "empty_document_upload"

    with pytest.raises(DomainValidationError) as too_large:
        helper_service._prepare_upload(
            mime_type="text/plain",
            original_filename="payload.txt",
            content_base64=encode_payload(b"12345"),
        )
    assert too_large.value.code == "document_too_large"

    storage = SimpleNamespace(
        save_file=lambda **_kwargs: None,
        delete_calls=[],
    )
    storage.delete_file = lambda **kwargs: storage.delete_calls.append(kwargs["storage_key"])
    session = SessionRecorder(flush_error=RuntimeError("flush failed"))
    service = documents_service.DocumentService(session, storage=storage)
    service.publisher = SimpleNamespace(record_event=lambda **_kwargs: [uuid4()])

    with pytest.raises(RuntimeError):
        service._save_document_bundle(
            document=SimpleNamespace(id=uuid4(), organization_id=actor.organization.id),
            version=SimpleNamespace(storage_key="documents/key.txt"),
            job=SimpleNamespace(id=uuid4()),
            content=b"payload",
            actor_user_id=actor.user.id,
            event_type="document.uploaded",
            metadata={},
            case=SimpleNamespace(status=CaseStatus.NEW),
            previous_case_status=CaseStatus.NEW,
        )
    assert storage.delete_calls == ["documents/key.txt"]

    review_service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    monkeypatch.setattr(review_service, "_get_document_for_actor", lambda **_kwargs: None)
    with pytest.raises(NotFoundError):
        review_service._review_document(
            actor=actor,
            document_id=uuid4(),
            decision="approved",
            reason="ok",
        )

    not_ready_document = SimpleNamespace(status=DocumentStatus.QUEUED)
    review_service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    monkeypatch.setattr(
        review_service,
        "_get_document_for_actor",
        lambda **_kwargs: not_ready_document,
    )
    with pytest.raises(DomainValidationError) as review_forbidden:
        review_service._review_document(
            actor=actor,
            document_id=uuid4(),
            decision="approved",
            reason="ok",
        )
    assert review_forbidden.value.code == "document_review_forbidden"

    ready_document = SimpleNamespace(
        id=uuid4(),
        case_id=uuid4(),
        organization_id=actor.organization.id,
        status=DocumentStatus.READY,
    )
    review_service = documents_service.DocumentService(SessionRecorder(), storage=SimpleNamespace())
    review_service.publisher = SimpleNamespace(record_event=lambda **_kwargs: [uuid4()])
    monkeypatch.setattr(review_service, "_get_document_for_actor", lambda **_kwargs: ready_document)
    monkeypatch.setattr(review_service, "_get_case_for_actor", lambda **_kwargs: None)
    with pytest.raises(NotFoundError):
        review_service._review_document(
            actor=actor,
            document_id=ready_document.id,
            decision="approved",
            reason="ok",
        )

    status_service = documents_service.DocumentService(
        SessionRecorder(scalars_values=[[DocumentStatus.APPROVED, DocumentStatus.READY]]),
        storage=SimpleNamespace(),
    )
    assert (
        status_service._calculate_case_status_after_review(
            case=SimpleNamespace(id=uuid4(), organization_id=actor.organization.id),
            current_document=SimpleNamespace(status=DocumentStatus.APPROVED),
        )
        == CaseStatus.IN_REVIEW
    )


def test_reporting_email_and_operations_helpers_cover_remaining_branches() -> None:
    assert reporting_service._serialize_datetime(datetime.now(UTC)).endswith("+00:00")
    assert emails_service._format_datetime(datetime(2030, 1, 1, 12, 0)).endswith("+00:00")

    with pytest.raises(PermissionDeniedError):
        operations_service.OperationsService._ensure_manage_permission(
            build_actor(role=OrganizationRole.MEMBER)
        )


def test_admin_notification_service_remaining_branches_are_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = build_actor(is_superuser=True)
    preference = SimpleNamespace(
        digest_schedule=AdminNotificationDigestSchedule.DAILY,
        digest_last_sent_at=None,
        digest_next_due_at=None,
    )
    preview = admin_notifications_service.AdminNotificationDigestPreview(
        total_count=1,
        unread_only=True,
        counts_by_type={AdminNotificationType.REVIEW_AUTO_OPENED.value: 1},
        notifications=[],
    )
    session = SessionRecorder(scalar_values=[preference])
    service = admin_notifications_service.AdminNotificationService(session)
    service.email_outbox = SimpleNamespace(dispatch_enqueued_emails=lambda ids: ids)
    monkeypatch.setattr(service, "_preview_digest_for_user", lambda **_kwargs: preview)
    monkeypatch.setattr(
        service,
        "_enqueue_digest_email",
        lambda **_kwargs: SimpleNamespace(id=uuid4()),
    )

    sent = service.send_digest(actor=actor, unread_only=True, limit=10)
    assert sent.sent is True
    assert preference.digest_last_sent_at is not None
    assert preference.digest_next_due_at is not None

    due_pref = SimpleNamespace(
        digest_schedule=AdminNotificationDigestSchedule.DAILY,
        digest_last_sent_at=None,
        digest_next_due_at=datetime.now(UTC),
    )
    due_user = SimpleNamespace(
        id=uuid4(),
        email="root@example.com",
        created_at=datetime.now(UTC),
        is_superuser=True,
        is_active=True,
    )
    session = SessionRecorder()
    session.execute = lambda _query: [(due_pref, due_user)]
    service = admin_notifications_service.AdminNotificationService(session)
    service.email_outbox = SimpleNamespace(dispatch_enqueued_emails=lambda ids: ids)
    monkeypatch.setattr(
        service,
        "_preview_digest_for_user",
        lambda **_kwargs: admin_notifications_service.AdminNotificationDigestPreview(
            total_count=0,
            unread_only=True,
            counts_by_type={},
            notifications=[],
        ),
    )
    monkeypatch.setattr(
        service,
        "_enqueue_digest_email",
        lambda **_kwargs: SimpleNamespace(id=uuid4()),
    )
    assert service.process_due_digests(limit=1) == 0
    assert due_pref.digest_next_due_at is not None

    existing_pref = SimpleNamespace(
        email_enabled=True,
        notify_on_review_auto_opened=True,
        notify_on_review_overdue_escalated=True,
        digest_schedule=AdminNotificationDigestSchedule.DAILY,
        digest_next_due_at=None,
        digest_last_sent_at=None,
    )
    session = SessionRecorder(scalar_values=[existing_pref])
    service = admin_notifications_service.AdminNotificationService(session)
    snapshot = service.update_preferences(
        actor=actor,
        payload=AdminNotificationPreferenceUpdateRequest(email_enabled=True),
    )
    assert snapshot.digest_next_due_at is not None

    with pytest.raises(NotFoundError):
        admin_notifications_service.AdminNotificationService(SessionRecorder()).mark_read(
            actor=actor,
            notification_id=uuid4(),
        )

    unread_notification = SimpleNamespace(read_at=None)
    session = SessionRecorder(scalars_values=[[unread_notification]])
    service = admin_notifications_service.AdminNotificationService(session)
    assert service.mark_all_read(actor=actor) == 1
    assert unread_notification.read_at is not None
    assert session.commits == 1

    service = admin_notifications_service.AdminNotificationService(SessionRecorder())
    monkeypatch.setattr(service, "_list_notifiable_superusers", lambda: [actor.user])
    monkeypatch.setattr(
        service,
        "_get_or_build_preference",
        lambda _user: SimpleNamespace(
            notify_on_review_overdue_escalated=False,
            email_enabled=True,
        ),
    )
    service.email_outbox = SimpleNamespace(
        enqueue_platform_admin_notification_email=lambda **_kwargs: SimpleNamespace(id=uuid4()),
        dispatch_enqueued_emails=lambda ids: ids,
    )
    service.notify_review_overdue_escalated(
        actor=actor,
        review=SimpleNamespace(
            id=uuid4(),
            organization=SimpleNamespace(id=uuid4(), name="Org", slug="org"),
            title="Review",
            priority=SimpleNamespace(value="high"),
            assigned_to=None,
        ),
        days_overdue=2,
    )

    existing = SimpleNamespace(user_id=actor.user.id)
    service = admin_notifications_service.AdminNotificationService(
        SessionRecorder(scalar_values=[existing])
    )
    assert service._get_or_create_preference(actor.user) is existing

    service = admin_notifications_service.AdminNotificationService(
        SessionRecorder(scalars_values=[[]])
    )
    assert (
        service._list_notification_models_for_user(
            user_id=actor.user.id,
            unread_only=True,
            notification_type=AdminNotificationType.REVIEW_AUTO_OPENED,
            limit=10,
            offset=0,
            created_after=datetime.now(UTC) - timedelta(days=1),
        )
        == []
    )

    assert (
        admin_notifications_service.AdminNotificationService._build_next_digest_due_at(
            schedule=AdminNotificationDigestSchedule.DISABLED,
            reference_time=datetime.now(UTC),
        )
        is None
    )
    assert (
        admin_notifications_service.AdminNotificationService(SessionRecorder())._load_organizations(
            set()
        )
        == {}
    )
    with pytest.raises(PermissionDeniedError):
        admin_notifications_service.AdminNotificationService._ensure_superuser(
            build_actor(is_superuser=False)
        )


def test_admin_review_service_remaining_branches_are_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = build_actor(is_superuser=True)
    service = admin_reviews_service.AdminReviewService(SessionRecorder())

    monkeypatch.setattr(service, "_ensure_superuser", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_list_active_reviews", lambda: [])
    assert service.list_review_workload(actor=actor, limit=10) == []
    assert service.list_attention_queue(actor=actor, limit=10) == []
    assert service.preview_auto_assignments(actor=actor, limit=10) == []

    review = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        assigned_to_user_id=None,
        priority=AdminReviewPriority.NORMAL,
        due_at=None,
        updated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        risk_score_snapshot=10,
    )
    monkeypatch.setattr(service, "_list_active_reviews", lambda: [review])
    monkeypatch.setattr(service, "_list_assignable_reviewers_with_load", lambda: [])
    assert service.preview_auto_assignments(actor=actor, limit=10) == []

    preview_org = admin_reviews_service.AdminReviewOrganizationRef(
        id=uuid4(),
        name="Org",
        slug="org",
        status=OrganizationStatus.ACTIVE,
    )
    preview_user = admin_reviews_service.AdminReviewUserRef(
        id=uuid4(),
        email="root@example.com",
        first_name="Root",
        last_name="Admin",
    )
    preview_item = admin_reviews_service.AdminReviewAutoAssignPreviewItem(
        review_id=uuid4(),
        organization=preview_org,
        title="Review",
        priority=AdminReviewPriority.NORMAL,
        due_at=None,
        attention_reasons=[],
        suggested_assignee=preview_user,
        current_assignee_load=1,
        projected_assignee_load=2,
    )
    skipped_review = SimpleNamespace(
        status=AdminReviewStatus.RESOLVED,
        assigned_to_user_id=preview_user.id,
    )
    service = admin_reviews_service.AdminReviewService(SessionRecorder())
    monkeypatch.setattr(service, "_ensure_superuser", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "preview_auto_assignments", lambda **_kwargs: [preview_item])
    monkeypatch.setattr(service, "_load_users", lambda _ids: {preview_user.id: preview_user})
    monkeypatch.setattr(service, "_get_review", lambda _review_id: skipped_review)
    result = service.auto_assign_reviews(
        actor=actor,
        payload=AdminReviewAutoAssignRequest(limit=1),
    )
    assert result.skipped_count == 1
    assert result.results[0].reason == "review_no_longer_unassigned"

    service = admin_reviews_service.AdminReviewService(SessionRecorder(scalars_values=[[]]))
    monkeypatch.setattr(service, "_ensure_superuser", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_build_review_list_items", lambda _reviews: {review.id: None})
    no_reason_review = SimpleNamespace(
        id=uuid4(),
        assigned_to_user_id=uuid4(),
        priority=AdminReviewPriority.NORMAL,
        due_at=None,
        updated_at=datetime.now(UTC),
    )
    monkeypatch.setattr(service, "_list_active_reviews", lambda: [no_reason_review])
    monkeypatch.setattr(
        service,
        "_build_review_list_items",
        lambda reviews: [
            SimpleNamespace(
                id=reviews[0].id,
                due_at=None,
                priority=AdminReviewPriority.NORMAL,
                updated_at=reviews[0].updated_at,
            )
        ],
    )
    monkeypatch.setattr(service, "_build_attention_reasons", lambda **_kwargs: [])
    assert service.list_attention_queue(actor=actor, limit=10) == []

    service = admin_reviews_service.AdminReviewService(SessionRecorder(scalars_values=[[]]))
    monkeypatch.setattr(service, "_ensure_superuser", lambda *_args, **_kwargs: None)
    assert (
        service.list_reviews(
            actor=actor,
            organization_id=None,
            status=None,
            priority=AdminReviewPriority.HIGH,
            assigned_to_user_id=None,
            assigned_to_me=False,
            search="tenant",
            limit=10,
        )
        == []
    )

    assert service._build_review_list_items([]) == []
    assert service._load_active_review_ids(set()) == {}
    assert service._load_organizations(set()) == {}

    with pytest.raises(DomainValidationError):
        service._resolve_assignee(uuid4())

    with pytest.raises(NotFoundError):
        service._get_review(uuid4())

    with pytest.raises(NotFoundError):
        service._get_organization(uuid4())

    with pytest.raises(PermissionDeniedError):
        admin_reviews_service.AdminReviewService._ensure_superuser(build_actor(is_superuser=False))

    assert service._priority_from_risk_score(120) == AdminReviewPriority.URGENT
    assert service._priority_from_risk_score(25) == AdminReviewPriority.NORMAL
    assert service._review_due_at(SimpleNamespace(due_at=None)) is None
    assert service._days_overdue(review=SimpleNamespace(due_at=None), now=datetime.now(UTC)) == 0
    assert (
        service._hours_until_due(
            review=SimpleNamespace(due_at=None),
            now=datetime.now(UTC),
        )
        is None
    )
    assert service._priority_sort_value(AdminReviewPriority.NORMAL) == 2
    aware = datetime.now(UTC)
    assert admin_reviews_service._to_utc(aware) is aware


def test_admin_review_update_assigns_optional_fields() -> None:
    actor = build_actor(is_superuser=True)
    review = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        title="Old title",
        summary="Old summary",
        status=AdminReviewStatus.OPEN,
        priority=AdminReviewPriority.LOW,
        due_at=None,
        resolved_at=None,
        assigned_to_user_id=None,
        risk_score_snapshot=5,
        risk_level_snapshot="low",
        anomaly_count_snapshot=1,
        top_anomaly_codes_json=[],
    )
    service = admin_reviews_service.AdminReviewService(SessionRecorder())
    service.publisher = SimpleNamespace(record_event=lambda **_kwargs: None)
    service._ensure_superuser = lambda *_args, **_kwargs: None
    service._get_review = lambda _review_id: review
    service._resolve_assignee = lambda _user_id: None
    service.get_review = lambda **_kwargs: review

    updated = service.update_review(
        actor=actor,
        review_id=review.id,
        payload=admin_reviews_service.AdminReviewUpdateRequest(
            title="New title",
            summary="New summary",
            priority=AdminReviewPriority.HIGH,
            due_at=datetime(2030, 1, 15, 12, 0, tzinfo=UTC),
        ),
    )

    assert updated is review
    assert review.title == "New title"
    assert review.summary == "New summary"
    assert review.priority == AdminReviewPriority.HIGH
    assert review.due_at == datetime(2030, 1, 15, 12, 0, tzinfo=UTC)


def test_schema_leftovers_are_covered() -> None:
    assert (
        admin_reviews_service.AdminReviewUpdateRequest.normalize_title.__func__(
            admin_reviews_service.AdminReviewUpdateRequest,
            "Valid title",
        )
        == "Valid title"
    )
