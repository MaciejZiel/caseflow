from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from urllib import error
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.v1.schemas.admin import (
    AdminBulkOrganizationStatusChangeRequest,
    AdminOrganizationStatusChangeRequest,
)
from app.api.v1.schemas.admin_reviews import AdminReviewUpdateRequest
from app.api.v1.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RegistrationRequest,
)
from app.api.v1.schemas.webhooks import WebhookEndpointUpdateRequest
from app.application.services import api_keys as api_keys_service
from app.application.services import auth as auth_service
from app.application.services import webhooks as webhook_service
from app.application.services.admin import AdminService
from app.application.services.admin import _serialize_datetime as admin_serialize
from app.application.services.api_keys import ApiKeyContext
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.domain.api_keys.models import ApiKeyScope
from app.domain.organizations.models import OrganizationStatus
from app.domain.webhooks.models import WebhookDeliveryStatus


class SessionRecorder:
    def __init__(
        self,
        *,
        scalar_values: list[object] | None = None,
        scalars_values: list[object] | None = None,
        get_values: dict[tuple[object, object], object] | None = None,
        flush_error: Exception | None = None,
    ) -> None:
        self.scalar_values = list(scalar_values or [])
        self.scalars_values = list(scalars_values or [])
        self.get_values = dict(get_values or {})
        self.flush_error = flush_error
        self.added: list[object] = []
        self.added_batches: list[list[object]] = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed: list[object] = []

    def scalar(self, _query):
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return None

    def scalars(self, _query):
        if self.scalars_values:
            return self.scalars_values.pop(0)
        return []

    def get(self, model, ident):
        return self.get_values.get((model, ident))

    def add(self, item) -> None:
        self.added.append(item)

    def add_all(self, items) -> None:
        self.added_batches.append(list(items))

    def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, item) -> None:
        self.refreshed.append(item)

    def execute(self, _query):
        return []


def test_auth_registration_conflicts_and_integrity_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conflict_service = auth_service.AuthService(SessionRecorder())
    monkeypatch.setattr(conflict_service, "_email_exists", lambda *_args: False)
    monkeypatch.setattr(conflict_service, "_organization_slug_exists", lambda *_args: True)

    with pytest.raises(ConflictError) as slug_taken:
        conflict_service.register_organization_owner(
            RegistrationRequest(
                organization_name="Acme",
                organization_slug="acme",
                first_name="Ada",
                last_name="Lovelace",
                email="ada@example.com",
                password="StrongPass123",
            )
        )
    assert slug_taken.value.code == "organization_slug_taken"

    session = SessionRecorder(flush_error=IntegrityError("insert", {}, RuntimeError("boom")))
    service = auth_service.AuthService(session)
    monkeypatch.setattr(service, "_email_exists", lambda *_args: False)
    monkeypatch.setattr(service, "_organization_slug_exists", lambda *_args: False)
    monkeypatch.setattr(auth_service, "hash_password", lambda _: "hashed-password")
    monkeypatch.setattr(
        auth_service,
        "create_auth_session",
        lambda **_kwargs: (SimpleNamespace(id=uuid4()), "refresh-token"),
    )

    with pytest.raises(ConflictError) as registration_conflict:
        service.register_organization_owner(
            RegistrationRequest(
                organization_name="Acme",
                organization_slug="acme",
                first_name="Ada",
                last_name="Lovelace",
                email="ada@example.com",
                password="StrongPass123",
            )
        )

    assert registration_conflict.value.code == "registration_conflict"
    assert session.rollbacks == 1


def test_auth_login_session_and_password_reset_guard_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inactive_user = SimpleNamespace(
        id=uuid4(),
        is_active=False,
        password_hash="hashed",
    )
    session = SessionRecorder(scalar_values=[inactive_user])
    service = auth_service.AuthService(session)
    monkeypatch.setattr(auth_service, "verify_password", lambda *_args: True)

    with pytest.raises(AuthenticationError):
        service.login(LoginRequest(email="ada@example.com", password="StrongPass123"))

    active_user = SimpleNamespace(id=uuid4(), is_active=True, password_hash="hashed")
    session = SessionRecorder(scalar_values=[active_user])
    service = auth_service.AuthService(session)
    monkeypatch.setattr(service, "_resolve_membership", lambda **_kwargs: None)

    with pytest.raises(AuthenticationError):
        service.login(LoginRequest(email="ada@example.com", password="StrongPass123"))

    inactive_org_membership = SimpleNamespace(
        organization=SimpleNamespace(status=OrganizationStatus.SUSPENDED),
    )
    session = SessionRecorder(scalar_values=[active_user])
    service = auth_service.AuthService(session)
    monkeypatch.setattr(service, "_resolve_membership", lambda **_kwargs: inactive_org_membership)

    with pytest.raises(AuthenticationError):
        service.login(LoginRequest(email="ada@example.com", password="StrongPass123"))

    logout_session = SimpleNamespace(revoked_at=datetime.now(UTC))
    no_commit_session = SessionRecorder()
    auth_service.AuthService(no_commit_session).logout_current_session(auth_session=logout_session)
    assert no_commit_session.commits == 0

    with pytest.raises(NotFoundError):
        auth_service.AuthService(SessionRecorder()).update_session_device_name(
            user=SimpleNamespace(id=uuid4()),
            session_id=uuid4(),
            device_name="Laptop",
        )

    with pytest.raises(NotFoundError):
        auth_service.AuthService(SessionRecorder()).revoke_session(
            user=SimpleNamespace(id=uuid4()),
            session_id=uuid4(),
        )

    already_revoked = SimpleNamespace(revoked_at=datetime.now(UTC), revoke_reason="previous")
    session = SessionRecorder(scalar_values=[already_revoked])
    result = auth_service.AuthService(session).revoke_session(
        user=SimpleNamespace(id=uuid4()),
        session_id=uuid4(),
    )
    assert result is already_revoked
    assert session.commits == 0

    inactive_reset_user = SimpleNamespace(id=uuid4(), is_active=False)
    service = auth_service.AuthService(SessionRecorder(scalar_values=[inactive_reset_user]))
    accepted = service.request_password_reset(PasswordResetRequest(email="inactive@example.com"))
    assert accepted.status == "accepted"

    active_reset_user = SimpleNamespace(id=uuid4(), is_active=True, email="ada@example.com")
    old_token = SimpleNamespace(revoked_at=None)
    outbox_calls: dict[str, object] = {}

    class FakeEmailOutboxService:
        def __init__(self, _session) -> None:
            pass

        def enqueue_password_reset_email(self, **kwargs):
            outbox_calls["enqueue"] = kwargs
            return SimpleNamespace(id=uuid4())

        def dispatch_enqueued_emails(self, ids) -> None:
            outbox_calls["dispatch"] = list(ids)

    session = SessionRecorder(
        scalar_values=[active_reset_user],
        scalars_values=[[old_token]],
    )
    service = auth_service.AuthService(session)
    monkeypatch.setattr(auth_service, "EmailOutboxService", FakeEmailOutboxService)
    monkeypatch.setattr(auth_service, "generate_opaque_token", lambda: "reset-token")
    monkeypatch.setattr(auth_service, "hash_opaque_token", lambda token: f"hashed:{token}")

    accepted = service.request_password_reset(PasswordResetRequest(email="ada@example.com"))
    assert accepted.status == "accepted"
    assert old_token.revoked_at is not None
    assert session.commits == 1
    assert outbox_calls["dispatch"]

    invalid_service = auth_service.AuthService(SessionRecorder(scalar_values=[None]))
    with pytest.raises(DomainValidationError) as invalid_token:
        invalid_service.confirm_password_reset(
            PasswordResetConfirmRequest(
                token="bad-token-1234567890123",
                password="NewStrongPass123",
            )
        )
    assert invalid_token.value.code == "invalid_password_reset_token"

    expired_token = SimpleNamespace(
        revoked_at=None,
        consumed_at=None,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        user=SimpleNamespace(is_active=True),
    )
    expired_service = auth_service.AuthService(SessionRecorder(scalar_values=[expired_token]))
    with pytest.raises(DomainValidationError) as expired:
        expired_service.confirm_password_reset(
            PasswordResetConfirmRequest(
                token="expired-token-1234567890",
                password="NewStrongPass123",
            )
        )
    assert expired.value.code == "password_reset_token_expired"

    inactive_user_token = SimpleNamespace(
        revoked_at=None,
        consumed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        user=SimpleNamespace(is_active=False),
    )
    inactive_service = auth_service.AuthService(
        SessionRecorder(scalar_values=[inactive_user_token])
    )
    with pytest.raises(AuthenticationError):
        inactive_service.confirm_password_reset(
            PasswordResetConfirmRequest(
                token="inactive-token-123456789",
                password="NewStrongPass123",
            )
        )

    active_user = SimpleNamespace(id=uuid4(), is_active=True, password_hash="old-hash")
    reset_token = SimpleNamespace(
        id=uuid4(),
        revoked_at=None,
        consumed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        user=active_user,
    )
    sibling_token = SimpleNamespace(revoked_at=None)
    session = SessionRecorder(
        scalar_values=[reset_token],
        scalars_values=[[sibling_token]],
    )
    service = auth_service.AuthService(session)
    monkeypatch.setattr(auth_service, "hash_password", lambda _: "new-hash")
    revoked_sessions: dict[str, object] = {}
    monkeypatch.setattr(
        service,
        "_revoke_user_sessions",
        lambda **kwargs: revoked_sessions.update(kwargs),
    )

    result = service.confirm_password_reset(
        PasswordResetConfirmRequest(
            token="okay-token-123456789012",
            password="NewStrongPass123",
        )
    )

    assert result.status == "password_reset"
    assert active_user.password_hash == "new-hash"
    assert sibling_token.revoked_at is not None
    assert revoked_sessions["reason"] == "password_reset"
    assert session.commits == 1


def test_auth_membership_activity_and_device_helpers_cover_remaining_paths() -> None:
    service = auth_service.AuthService(SessionRecorder(scalars_values=[[]]))
    assert service._resolve_membership(user_id=uuid4(), organization_slug=None) is None

    multiple_service = auth_service.AuthService(
        SessionRecorder(
            scalars_values=[
                [
                    SimpleNamespace(joined_at=datetime.now(UTC)),
                    SimpleNamespace(joined_at=datetime.now(UTC) + timedelta(seconds=1)),
                ]
            ]
        )
    )
    with pytest.raises(DomainValidationError) as requires_org:
        multiple_service._resolve_membership(user_id=uuid4(), organization_slug=None)
    assert requires_org.value.code == "organization_selection_required"

    revoked = SimpleNamespace(revoked_at=datetime.now(UTC))
    with pytest.raises(AuthenticationError):
        auth_service.AuthService(SessionRecorder())._ensure_auth_session_is_active(revoked)

    expired = SimpleNamespace(
        revoked_at=None,
        refresh_token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    with pytest.raises(AuthenticationError):
        auth_service.AuthService(SessionRecorder())._ensure_auth_session_is_active(expired)

    inactive_user = SimpleNamespace(
        revoked_at=None,
        refresh_token_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        user=SimpleNamespace(is_active=False),
    )
    with pytest.raises(AuthenticationError):
        auth_service.AuthService(SessionRecorder())._ensure_auth_session_is_active(inactive_user)

    inactive_membership = SimpleNamespace(
        revoked_at=None,
        refresh_token_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        user=SimpleNamespace(is_active=True),
        membership=SimpleNamespace(is_active=False),
    )
    with pytest.raises(AuthenticationError):
        auth_service.AuthService(SessionRecorder())._ensure_auth_session_is_active(
            inactive_membership
        )

    inactive_org = SimpleNamespace(
        revoked_at=None,
        refresh_token_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        user=SimpleNamespace(is_active=True),
        membership=SimpleNamespace(is_active=True),
        organization=SimpleNamespace(status=OrganizationStatus.SUSPENDED),
    )
    with pytest.raises(AuthenticationError):
        auth_service.AuthService(SessionRecorder())._ensure_auth_session_is_active(inactive_org)

    auth_session = SimpleNamespace()
    assert auth_service.touch_auth_session_activity(auth_session, client_context=None) is False

    now = datetime.now(UTC)
    settings = SimpleNamespace(auth_session_activity_update_interval_seconds=60)
    assert auth_service._should_update_auth_session_activity(
        auth_session=SimpleNamespace(last_seen_at=None),
        client_context=auth_service.AuthClientContext(client_ip="1.1.1.1", user_agent="ua"),
        settings=settings,
        now=now,
    )
    assert auth_service._should_update_auth_session_activity(
        auth_session=SimpleNamespace(
            last_seen_at=now,
            last_seen_ip="2.2.2.2",
            last_seen_user_agent="ua",
        ),
        client_context=auth_service.AuthClientContext(client_ip="1.1.1.1", user_agent="ua"),
        settings=settings,
        now=now,
    )
    assert auth_service._should_update_auth_session_activity(
        auth_session=SimpleNamespace(
            last_seen_at=now,
            last_seen_ip="1.1.1.1",
            last_seen_user_agent="old-ua",
        ),
        client_context=auth_service.AuthClientContext(client_ip="1.1.1.1", user_agent="ua"),
        settings=settings,
        now=now,
    )
    assert auth_service._should_update_auth_session_activity(
        auth_session=SimpleNamespace(
            last_seen_at=now - timedelta(minutes=5),
            last_seen_ip="1.1.1.1",
            last_seen_user_agent="ua",
        ),
        client_context=auth_service.AuthClientContext(client_ip="1.1.1.1", user_agent="ua"),
        settings=settings,
        now=now,
    )

    assert auth_service.infer_device_name(None) == "Unknown Device"
    assert auth_service.infer_device_name("Mozilla iPhone") == "iPhone"
    assert auth_service.infer_device_name("Mozilla iPad") == "iPad"
    assert auth_service.infer_device_name("Android Mobile Safari") == "Android Phone"
    assert auth_service.infer_device_name("Android Tablet") == "Android Device"
    assert auth_service.infer_device_name("Mozilla Windows NT") == "Windows Device"
    assert auth_service.infer_device_name("Mozilla Macintosh") == "macOS Device"
    assert auth_service.infer_device_name("Mozilla Linux") == "Linux Device"

    aware = datetime.now(UTC)
    assert auth_service._to_utc(aware) is aware


def test_webhook_service_update_retry_replay_and_queue_guard_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        membership=SimpleNamespace(role="owner"),
        organization=SimpleNamespace(id=uuid4()),
    )

    session = SessionRecorder()
    service = webhook_service.WebhookService(session)
    monkeypatch.setattr(service, "_ensure_manage_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_get_endpoint_for_actor", lambda **_kwargs: None)

    with pytest.raises(NotFoundError):
        service.update_endpoint(
            actor=actor,
            endpoint_id=uuid4(),
            payload=WebhookEndpointUpdateRequest(is_active=False),
        )

    endpoint = SimpleNamespace(
        id=uuid4(),
        target_url="https://old.example.test/webhook",
        signing_secret="old-secret",
        subscribed_event_types_json=["case.created"],
        is_active=True,
    )
    session = SessionRecorder()
    service = webhook_service.WebhookService(session)
    service.publisher = SimpleNamespace(record_event=lambda **_kwargs: [uuid4()])
    monkeypatch.setattr(service, "_ensure_manage_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_get_endpoint_for_actor", lambda **_kwargs: endpoint)

    result = service.update_endpoint(
        actor=actor,
        endpoint_id=endpoint.id,
        payload=WebhookEndpointUpdateRequest(
            target_url="https://new.example.test/webhook",
            signing_secret="new-secret-123456",
            subscribed_event_types=["document.approved"],
            is_active=False,
        ),
    )

    assert result.endpoint.target_url == "https://new.example.test/webhook"
    assert result.endpoint.signing_secret == "new-secret-123456"
    assert result.endpoint.subscribed_event_types_json == ["document.approved"]
    assert result.endpoint.is_active is False
    assert session.commits == 1

    service = webhook_service.WebhookService(
        SessionRecorder(scalars_values=[[SimpleNamespace(endpoint_id=uuid4())]])
    )
    dispatch_calls: list[object] = []
    monkeypatch.setattr(
        service,
        "_dispatch_single_delivery",
        lambda **kwargs: dispatch_calls.append(kwargs),
    )
    service.session.scalar = lambda _query: None
    service.dispatch_deliveries([uuid4()])
    assert dispatch_calls == []

    service = webhook_service.WebhookService(SessionRecorder(scalar_values=[None]))
    monkeypatch.setattr(service, "_ensure_manage_permission", lambda *_args, **_kwargs: None)
    with pytest.raises(NotFoundError):
        service.retry_delivery(actor=actor, delivery_id=uuid4())

    non_failed_delivery = SimpleNamespace(status=WebhookDeliveryStatus.DELIVERED)
    service = webhook_service.WebhookService(SessionRecorder(scalar_values=[non_failed_delivery]))
    monkeypatch.setattr(service, "_ensure_manage_permission", lambda *_args, **_kwargs: None)
    with pytest.raises(DomainValidationError) as retry_forbidden:
        service.retry_delivery(actor=actor, delivery_id=uuid4())
    assert retry_forbidden.value.code == "webhook_delivery_retry_forbidden"

    service = webhook_service.WebhookService(SessionRecorder(scalar_values=[None]))
    monkeypatch.setattr(service, "_ensure_manage_permission", lambda *_args, **_kwargs: None)
    with pytest.raises(NotFoundError):
        service.replay_delivery(actor=actor, delivery_id=uuid4())

    source_delivery = SimpleNamespace(
        id=uuid4(),
        organization_id=actor.organization.id,
        endpoint_id=uuid4(),
        event_type="case.created",
        request_body_json={"ok": True},
    )
    service = webhook_service.WebhookService(SessionRecorder(scalar_values=[source_delivery]))
    monkeypatch.setattr(service, "_ensure_manage_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_get_endpoint_for_actor", lambda **_kwargs: None)
    with pytest.raises(NotFoundError):
        service.replay_delivery(actor=actor, delivery_id=uuid4())

    due_delivery = SimpleNamespace(id=uuid4())
    session = SessionRecorder(
        scalars_values=[[due_delivery.id]],
        scalar_values=[None],
    )
    service = webhook_service.WebhookService(session)
    due_ids = service.process_due_deliveries(limit=1)
    assert due_ids == [due_delivery.id]
    assert session.commits == 0


def test_webhook_http_error_and_admin_helper_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SessionRecorder()
    service = webhook_service.WebhookService(session)
    service.settings = SimpleNamespace(webhook_retry_base_delay_seconds=5)

    delivery = SimpleNamespace(
        request_body_json={"case": "123"},
        event_type="case.created",
        attempts=0,
        status=WebhookDeliveryStatus.PENDING,
        http_status=None,
        response_body_excerpt=None,
        delivered_at=None,
        next_retry_at=None,
    )
    endpoint = SimpleNamespace(
        target_url="https://hooks.example.test/caseflow",
        signing_secret="webhook-secret",
    )

    def failing_urlopen(_req, timeout: int = 0):
        raise error.HTTPError(
            url="https://hooks.example.test/caseflow",
            code=503,
            msg="unavailable",
            hdrs=None,
            fp=BytesIO(b'{"error":"down"}'),
        )

    monkeypatch.setattr(webhook_service.request, "urlopen", failing_urlopen)
    service._dispatch_single_delivery(delivery=delivery, endpoint=endpoint)

    assert delivery.status == WebhookDeliveryStatus.FAILED
    assert delivery.http_status == 503
    assert '{"error":"down"}' in delivery.response_body_excerpt
    assert delivery.next_retry_at is not None
    assert session.commits == 1

    assert AdminOrganizationStatusChangeRequest(reason=None).reason is None
    assert (
        AdminBulkOrganizationStatusChangeRequest(
            organization_ids=[uuid4()],
            action="suspend",
            reason=None,
        ).reason
        is None
    )
    assert AdminReviewUpdateRequest.normalize_title.__func__(AdminReviewUpdateRequest, None) is None
    assert (
        AdminReviewUpdateRequest.normalize_summary.__func__(AdminReviewUpdateRequest, None) is None
    )
    assert (
        WebhookEndpointUpdateRequest.validate_target_url.__func__(
            WebhookEndpointUpdateRequest,
            None,
        )
        is None
    )
    assert (
        WebhookEndpointUpdateRequest.validate_subscribed_event_types.__func__(
            WebhookEndpointUpdateRequest,
            None,
        )
        is None
    )
    assert ApiKeyContext(
        api_key=SimpleNamespace(scopes_json=["cases:read", "documents:read"])
    ).scopes == {
        ApiKeyScope.CASES_READ,
        ApiKeyScope.DOCUMENTS_READ,
    }
    aware = datetime.now(UTC)
    assert api_keys_service._to_utc(aware) is aware

    admin_service = AdminService(SessionRecorder())
    archived_org = SimpleNamespace(id=uuid4(), status=OrganizationStatus.ARCHIVED)
    monkeypatch.setattr(admin_service, "_get_organization", lambda *_args: archived_org)
    monkeypatch.setattr(admin_service, "_ensure_superuser", lambda *_args: None)
    actor = SimpleNamespace(
        user=SimpleNamespace(id=uuid4(), is_superuser=True),
        organization=SimpleNamespace(id=uuid4()),
    )

    with pytest.raises(DomainValidationError) as suspend_archived:
        admin_service.suspend_organization(actor=actor, organization_id=uuid4(), reason=None)
    assert suspend_archived.value.code == "archived_organization_suspend_forbidden"

    with pytest.raises(DomainValidationError) as reactivate_archived:
        admin_service.reactivate_organization(actor=actor, organization_id=uuid4(), reason=None)
    assert reactivate_archived.value.code == "archived_organization_reactivation_forbidden"

    with pytest.raises(PermissionDeniedError):
        AdminService._ensure_superuser(SimpleNamespace(user=SimpleNamespace(is_superuser=False)))

    with pytest.raises(NotFoundError):
        AdminService(SessionRecorder())._get_organization(uuid4())

    assert AdminService._risk_level_from_score(120) == "critical"
    assert AdminService._risk_level_from_score(25) == "medium"
    assert AdminService._risk_level_from_score(5) == "low"
    assert admin_serialize(datetime.now(UTC)).endswith("+00:00")
