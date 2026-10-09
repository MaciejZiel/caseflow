from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from app.api.deps import auth as auth_deps
from app.api.v1.routes import webhooks as webhook_routes
from app.api.v1.schemas.admin import (
    AdminBulkOrganizationStatusChangeRequest,
    AdminOrganizationStatusChangeRequest,
)
from app.api.v1.schemas.admin_notifications import AdminNotificationPreferenceUpdateRequest
from app.api.v1.schemas.admin_reviews import (
    AdminReviewAutoAssignRequest,
    AdminReviewCommentCreateRequest,
    AdminReviewEscalateOverdueRequest,
    AdminReviewUpdateRequest,
    _normalize_optional_text,
    _normalize_title,
)
from app.api.v1.schemas.api_keys import ApiKeyCreateRequest
from app.api.v1.schemas.documents import DocumentRejectRequest
from app.api.v1.schemas.webhooks import WebhookEndpointUpdateRequest
from app.application.services import assistant as assistant_service
from app.application.services.reporting import ReportingService, _serialize_datetime
from app.application.services.superusers import SuperuserService
from app.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.domain.api_keys.models import ApiKeyScope
from app.domain.assistant.models import AssistantPromptMode
from app.domain.organizations.models import OrganizationRole, OrganizationStatus
from tests.unit.test_foundational_coverage import build_starlette_request


@pytest.mark.asyncio
async def test_get_current_actor_rejects_inactive_organization_even_for_valid_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "sub": str(uuid4()),
        "organization_id": str(uuid4()),
        "session_id": str(uuid4()),
    }
    monkeypatch.setattr(auth_deps, "decode_access_token", lambda _: payload)

    suspended_org = SimpleNamespace(status=OrganizationStatus.SUSPENDED)
    membership = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        role=OrganizationRole.OWNER,
        organization=suspended_org,
    )
    user = SimpleNamespace(is_active=True, is_superuser=False)
    auth_session = SimpleNamespace(
        refresh_token_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        user=user,
        membership=membership,
        organization=suspended_org,
    )
    session = SimpleNamespace(scalar=lambda _: auth_session, commit=lambda: None)

    with pytest.raises(AuthenticationError):
        await auth_deps.get_current_actor(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            session,
            build_starlette_request(),
        )


@pytest.mark.asyncio
async def test_update_webhook_endpoint_route_uses_service_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint_id = uuid4()
    endpoint = SimpleNamespace(
        id=endpoint_id,
        target_url="https://updated.example.test/webhook",
        subscribed_event_types_json=["case.created"],
        is_active=False,
        created_by=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    captured: dict[str, object] = {}

    class FakeWebhookService:
        def __init__(self, session) -> None:
            captured["session"] = session

        def update_endpoint(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(endpoint=endpoint)

    monkeypatch.setattr(webhook_routes, "WebhookService", FakeWebhookService)

    response = await webhook_routes.update_webhook_endpoint(
        endpoint_id=endpoint_id,
        payload=WebhookEndpointUpdateRequest(is_active=False),
        actor=object(),
        session=object(),
    )

    assert response.id == endpoint_id
    assert response.target_url == endpoint.target_url
    assert captured["endpoint_id"] == endpoint_id


def test_admin_schema_reason_normalizers_accept_none() -> None:
    single = AdminOrganizationStatusChangeRequest()
    bulk = AdminBulkOrganizationStatusChangeRequest(
        organization_ids=[uuid4()],
        action="suspend",
    )

    assert single.reason is None
    assert bulk.reason is None


def test_admin_notification_preferences_require_at_least_one_field() -> None:
    with pytest.raises(ValidationError):
        AdminNotificationPreferenceUpdateRequest()


def test_admin_review_schema_edge_cases_are_covered() -> None:
    with pytest.raises(ValueError):
        _normalize_title("   ")

    assert _normalize_optional_text(None) is None

    with pytest.raises(ValidationError):
        AdminReviewUpdateRequest()

    with pytest.raises(ValidationError):
        AdminReviewCommentCreateRequest(body="   ")

    assert AdminReviewUpdateRequest(title=None, status="open").title is None
    assert AdminReviewEscalateOverdueRequest(comment_body=None).comment_body is None
    assert AdminReviewAutoAssignRequest(comment_body=None).comment_body is None


def test_api_key_document_and_webhook_schema_none_or_error_branches() -> None:
    request = ApiKeyCreateRequest(
        name="Primary integration key",
        description=None,
        scopes=[ApiKeyScope.CASES_READ],
    )

    assert request.description is None

    with pytest.raises(ValidationError):
        DocumentRejectRequest(reason="   ")

    assert WebhookEndpointUpdateRequest.validate_target_url(None) is None
    assert WebhookEndpointUpdateRequest.validate_subscribed_event_types(None) is None


def test_assistant_build_grounded_answer_covers_archived_due_date_and_empty_evidence() -> None:
    case = SimpleNamespace(
        title="Archived due-date case",
        status=SimpleNamespace(value="in_review"),
        priority=SimpleNamespace(value="high"),
        due_date=datetime(2030, 1, 15, 12, 0, tzinfo=UTC),
        archived_at=datetime(2030, 1, 20, 9, 0, tzinfo=UTC),
    )

    answer = assistant_service.AssistantService(SimpleNamespace())._build_grounded_answer(
        case=case,
        question="???",
        prompt_mode=AssistantPromptMode.NEXT_ACTIONS,
        snippets=[],
    )

    assert "Due date: 2030-01-15." in answer
    assert "No documents are attached to this case yet" in answer
    assert "The case is archived" in answer


def test_assistant_helpers_cover_token_and_snippet_serialization_branches() -> None:
    assert assistant_service._extract_tokens("a bb ccc") == []

    snippet = assistant_service.GroundedDocumentSnippet(
        document_id=uuid4(),
        document_title="Failed invoice",
        document_type="invoice",
        document_status="failed",
        document_version_id=None,
        original_filename=None,
        excerpt="x" * 700,
        score=3,
    )

    payload = assistant_service._snippet_to_json(snippet)

    assert payload["document_version_id"] is None
    assert len(payload["excerpt"]) == 500


def test_reporting_permission_and_datetime_helpers_cover_remaining_branches() -> None:
    actor = SimpleNamespace(
        membership=SimpleNamespace(role=OrganizationRole.MEMBER),
        organization=SimpleNamespace(id=uuid4()),
    )

    with pytest.raises(PermissionDeniedError):
        ReportingService(SimpleNamespace()).case_summary(actor=actor)

    naive = datetime(2030, 1, 15, 12, 0)
    assert _serialize_datetime(naive).endswith("+00:00")


def test_superuser_service_raises_not_found_for_unknown_user() -> None:
    service = SuperuserService(SimpleNamespace(scalar=lambda _: None))

    with pytest.raises(NotFoundError):
        service.set_superuser_status(email="missing@example.com", is_superuser=True)
