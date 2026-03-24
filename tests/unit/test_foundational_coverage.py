from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import api_keys as api_keys_deps
from app.api.deps import auth as auth_deps
from app.api.middleware import _set_default_security_headers, register_http_middleware
from app.api.request_utils import extract_client_ip, extract_user_agent
from app.api.v1.routes import assistant as assistant_routes
from app.api.v1.routes import ops as ops_routes
from app.api.v1.schemas.api_keys import ApiKeyCreateRequest
from app.api.v1.schemas.api_keys import _to_utc as api_key_to_utc
from app.api.v1.schemas.auth import (
    AuthSessionUpdateRequest,
    LoginRequest,
    PasswordResetConfirmRequest,
    RegistrationRequest,
)
from app.api.v1.schemas.cases import CaseUpdateRequest
from app.api.v1.schemas.organizations import (
    InvitationCreateRequest,
    OrganizationMemberUpdateRequest,
)
from app.api.v1.schemas.webhooks import (
    WebhookEndpointCreateRequest,
    WebhookEndpointUpdateRequest,
)
from app.application.services.api_keys import ApiKeyContext
from app.core.config import Settings
from app.core.errors import AuthenticationError, DomainValidationError, PermissionDeniedError
from app.domain.api_keys.models import ApiKeyScope
from app.domain.assistant.models import AssistantMessageRole, AssistantPromptMode
from app.domain.cases.models import CaseStatus
from app.domain.emails.models import OutboundEmail
from app.domain.organizations.models import OrganizationRole, OrganizationStatus
from app.infrastructure.db import session as db_session
from app.infrastructure.email import smtp as smtp_module
from app.infrastructure.observability import metrics as metrics_module
from app.infrastructure.security import passwords as password_module
from app.infrastructure.security import tokens as token_module
from app.infrastructure.storage.local import LocalFileStorage
from app.workers import documents as document_worker
from app.workers import retries as retry_worker


def build_starlette_request(
    *,
    path: str = "/",
    method: str = "GET",
    headers: dict[str, str] | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 1234),
    scheme: str = "http",
    app: FastAPI | None = None,
):
    from starlette.requests import Request

    app = app or FastAPI()
    if not hasattr(app.state, "settings"):
        app.state.settings = SimpleNamespace(trust_proxy_headers=False)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": scheme,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {}).items()
        ],
        "client": client,
        "server": ("testserver", 80),
        "app": app,
    }
    return Request(scope)


class DummyLogger:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.exception_calls: list[tuple[str, dict[str, object]]] = []

    def bind(self, **_: object) -> DummyLogger:
        return self

    def info(self, event: str, **kwargs: object) -> None:
        self.info_calls.append((event, kwargs))

    def exception(self, event: str, **kwargs: object) -> None:
        self.exception_calls.append((event, kwargs))


@pytest.mark.asyncio
async def test_require_api_key_rejects_missing_or_blank_header() -> None:
    dependency = api_keys_deps.require_api_key(ApiKeyScope.CASES_READ)
    session = SimpleNamespace()
    request = build_starlette_request()

    with pytest.raises(AuthenticationError):
        await dependency(None, session, request)

    with pytest.raises(AuthenticationError):
        await dependency("   ", session, request)


@pytest.mark.asyncio
async def test_require_api_key_strips_header_and_passes_scopes(monkeypatch) -> None:
    expected_context = ApiKeyContext(api_key=SimpleNamespace(organization=object(), scopes_json=[]))
    captured: dict[str, object] = {}

    class FakeApiKeyService:
        def __init__(self, session) -> None:
            captured["session"] = session

        def authenticate_api_key(self, **kwargs):
            captured.update(kwargs)
            return expected_context

    monkeypatch.setattr(api_keys_deps, "ApiKeyService", FakeApiKeyService)
    request = build_starlette_request(client=("203.0.113.5", 9000))
    dependency = api_keys_deps.require_api_key(ApiKeyScope.CASES_READ, ApiKeyScope.DOCUMENTS_READ)

    result = await dependency("  plaintext-key  ", object(), request)

    assert result is expected_context
    assert captured["raw_key"] == "plaintext-key"
    assert captured["client_ip"] == "203.0.113.5"
    assert captured["required_scopes"] == {ApiKeyScope.CASES_READ, ApiKeyScope.DOCUMENTS_READ}


@pytest.mark.asyncio
async def test_get_current_actor_rejects_missing_and_invalid_bearer_credentials() -> None:
    request = build_starlette_request()

    with pytest.raises(AuthenticationError):
        await auth_deps.get_current_actor(None, SimpleNamespace(), request)

    credentials = HTTPAuthorizationCredentials(scheme="Basic", credentials="token")
    with pytest.raises(AuthenticationError):
        await auth_deps.get_current_actor(credentials, SimpleNamespace(), request)


@pytest.mark.asyncio
async def test_get_current_actor_rejects_invalid_auth_session_states(monkeypatch) -> None:
    payload = {
        "sub": str(uuid4()),
        "organization_id": str(uuid4()),
        "session_id": str(uuid4()),
    }
    request = build_starlette_request(headers={"User-Agent": "CaseFlowTest/1.0"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")
    monkeypatch.setattr(auth_deps, "decode_access_token", lambda _: payload)

    session = SimpleNamespace(scalar=lambda _: None, commit=lambda: None)
    with pytest.raises(AuthenticationError):
        await auth_deps.get_current_actor(credentials, session, request)

    inactive_org = SimpleNamespace(status=OrganizationStatus.SUSPENDED)
    active_membership = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        role=OrganizationRole.OWNER,
        organization=inactive_org,
    )
    active_user = SimpleNamespace(is_active=True, is_superuser=False)
    expired_session = SimpleNamespace(
        refresh_token_expires_at=datetime.now(UTC) - timedelta(minutes=1),
        user=active_user,
        membership=active_membership,
        organization=inactive_org,
    )
    session = SimpleNamespace(scalar=lambda _: expired_session, commit=lambda: None)
    with pytest.raises(AuthenticationError):
        await auth_deps.get_current_actor(credentials, session, request)

    valid_org = SimpleNamespace(status=OrganizationStatus.ACTIVE)
    inactive_membership = SimpleNamespace(
        id=uuid4(),
        is_active=False,
        role=OrganizationRole.OWNER,
        organization=valid_org,
    )
    active_but_invalid_session = SimpleNamespace(
        refresh_token_expires_at=datetime.now(UTC) + timedelta(minutes=30),
        user=active_user,
        membership=inactive_membership,
        organization=valid_org,
    )
    session = SimpleNamespace(scalar=lambda _: active_but_invalid_session, commit=lambda: None)
    with pytest.raises(AuthenticationError):
        await auth_deps.get_current_actor(credentials, session, request)


@pytest.mark.asyncio
async def test_get_current_actor_commits_activity_and_supports_superuser(monkeypatch) -> None:
    payload = {
        "sub": str(uuid4()),
        "organization_id": str(uuid4()),
        "session_id": str(uuid4()),
    }
    monkeypatch.setattr(auth_deps, "decode_access_token", lambda _: payload)
    monkeypatch.setattr(auth_deps, "touch_auth_session_activity", lambda *_args, **_kwargs: True)

    organization = SimpleNamespace(status=OrganizationStatus.ACTIVE)
    membership = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        role=OrganizationRole.OWNER,
        organization=organization,
    )
    user = SimpleNamespace(is_active=True, is_superuser=True)
    auth_session = SimpleNamespace(
        refresh_token_expires_at=datetime.now(UTC) + timedelta(minutes=30),
        user=user,
        membership=membership,
        organization=organization,
    )
    session = SimpleNamespace(
        scalar=lambda _: auth_session,
        commit=lambda: setattr(session, "committed", True),
    )
    request = build_starlette_request(
        headers={"User-Agent": " CaseFlowTest/1.0 "},
        client=("198.51.100.10", 3210),
    )

    actor = await auth_deps.get_current_actor(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
        session,
        request,
    )

    assert actor.user is user
    assert actor.membership is membership
    assert session.committed is True
    assert await auth_deps.get_current_superuser_actor(actor) is actor


@pytest.mark.asyncio
async def test_get_current_superuser_actor_rejects_non_superuser() -> None:
    actor = SimpleNamespace(user=SimpleNamespace(is_superuser=False))

    with pytest.raises(PermissionDeniedError):
        await auth_deps.get_current_superuser_actor(actor)


def test_auth_helper_functions_cover_missing_branches() -> None:
    assert auth_deps._parse_session_id({"session_id": str(uuid4())})
    with pytest.raises(AuthenticationError):
        auth_deps._parse_session_id({})

    aware_value = datetime.now(UTC)
    assert auth_deps._to_utc(aware_value) == aware_value
    naive_value = datetime.now()
    assert auth_deps._to_utc(naive_value).tzinfo == UTC


@pytest.mark.asyncio
async def test_middleware_records_500_responses_and_exception_paths(monkeypatch) -> None:
    recorded_requests: list[dict[str, object]] = []
    recorded_errors: list[dict[str, object]] = []
    logger = DummyLogger()

    monkeypatch.setattr(
        "app.api.middleware.record_http_request",
        lambda **kwargs: recorded_requests.append(kwargs),
    )
    monkeypatch.setattr(
        "app.api.middleware.record_http_error",
        lambda **kwargs: recorded_errors.append(kwargs),
    )

    app = FastAPI()
    app.state.settings = SimpleNamespace(
        cors_allowed_origins=[],
        app_env="test",
        trusted_host_patterns=[],
        security_headers_enabled=True,
        security_hsts_max_age_seconds=0,
    )
    app.state.logger = logger
    register_http_middleware(app)

    @app.get("/broken")
    async def broken():
        raise RuntimeError("boom")

    @app.get("/degraded")
    async def degraded():
        return Response(status_code=503)

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        broken_response = await client.get("/broken", headers={"X-Request-ID": "req-1"})
        degraded_response = await client.get("/degraded")

    assert broken_response.status_code == 500
    assert degraded_response.status_code == 503
    assert any(call["status_code"] == 500 for call in recorded_requests)
    assert any(call["status_code"] == 503 for call in recorded_errors)
    assert logger.exception_calls


def test_set_default_security_headers_adds_hsts_for_https_requests() -> None:
    response = Response()
    request = build_starlette_request(scheme="https")

    _set_default_security_headers(response, request=request, hsts_max_age_seconds=3600)

    assert response.headers["Strict-Transport-Security"] == "max-age=3600; includeSubDomains"


def test_request_utils_handle_forwarded_ips_and_missing_values() -> None:
    app = FastAPI()
    app.state.settings = SimpleNamespace(trust_proxy_headers=True)
    request = build_starlette_request(
        app=app,
        headers={"X-Forwarded-For": "198.51.100.25, 127.0.0.1", "User-Agent": " TestAgent/1.0 "},
        client=("127.0.0.1", 5000),
    )
    assert extract_client_ip(request) == "198.51.100.25"
    assert extract_user_agent(request) == "TestAgent/1.0"

    empty_forwarded = build_starlette_request(
        app=app,
        headers={"X-Forwarded-For": "   "},
        client=None,
    )
    assert extract_client_ip(empty_forwarded) is None
    assert extract_user_agent(build_starlette_request(headers={})) is None


def test_settings_parse_csv_settings_covers_none_and_csv_values() -> None:
    assert Settings.parse_csv_settings(None) == []
    assert Settings.parse_csv_settings(" http://a.test , http://b.test ") == [
        "http://a.test",
        "http://b.test",
    ]
    assert Settings.parse_csv_settings(["a", "b"]) == ["a", "b"]


def test_security_helpers_cover_invalid_token_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        token_module,
        "get_settings",
        lambda: SimpleNamespace(
            access_token_ttl_minutes=15,
            secret_key="test-secret-key-with-32-plus-bytes",
        ),
    )
    token, expires_in = token_module.create_access_token(
        user_id=uuid4(),
        organization_id=uuid4(),
        role="owner",
        session_id=uuid4(),
    )
    assert expires_in == 900
    assert token_module.decode_access_token(token)["type"] == "access"

    wrong_type = jwt.encode(
        {"type": "refresh"},
        "test-secret-key-with-32-plus-bytes",
        algorithm=token_module.JWT_ALGORITHM,
    )
    with pytest.raises(AuthenticationError):
        token_module.decode_access_token(wrong_type)

    with pytest.raises(AuthenticationError):
        token_module.decode_access_token("not-a-jwt")

    encoded = password_module.hash_password("StrongPass123")
    assert password_module.verify_password("StrongPass123", encoded) is True
    assert password_module.verify_password(
        "StrongPass123",
        encoded.replace(password_module.PASSWORD_ALGORITHM, "argon2", 1),
    ) is False


def test_local_storage_covers_stream_delete_url_and_traversal(tmp_path) -> None:
    storage = LocalFileStorage(base_path=tmp_path)
    storage.save_file(storage_key="cases/demo/file.txt", content=b"hello")

    with storage.get_file_stream(storage_key="cases/demo/file.txt") as stream:
        assert stream.read() == b"hello"

    assert storage.read_file(storage_key="cases/demo/file.txt") == b"hello"
    assert storage.build_public_or_signed_url(storage_key="cases/demo/file.txt") == (
        "local://cases/demo/file.txt"
    )
    storage.delete_file(storage_key="cases/demo/file.txt")
    storage.delete_file(storage_key="cases/demo/file.txt")
    assert LocalFileStorage.sanitize_filename("../ messy file ?.txt") == "messy_file_.txt"

    with pytest.raises(ValueError):
        storage.read_file(storage_key="../secrets.txt")


def test_database_and_metrics_helpers_cover_failure_paths(monkeypatch) -> None:
    class BrokenEngine:
        def connect(self):
            raise SQLAlchemyError("db down")

    monkeypatch.setattr(db_session, "get_engine", lambda: BrokenEngine())
    assert db_session.database_is_ready() is False

    metrics_module.record_http_error(method="GET", path="/boom", status_code=500)


def test_smtp_sink_covers_missing_host_and_plain_from_header(monkeypatch) -> None:
    monkeypatch.setattr(
        smtp_module,
        "get_settings",
        lambda: SimpleNamespace(
            smtp_host=None,
            smtp_port=587,
            smtp_timeout_seconds=10,
            smtp_use_ssl=False,
            smtp_use_starttls=True,
            smtp_username=None,
            smtp_password=None,
            smtp_from_email="caseflow@example.com",
            smtp_from_name="",
        ),
    )
    sink = smtp_module.SmtpEmailSink()
    email = OutboundEmail(
        organization_id=None,
        template_key="invite",
        recipient_email="user@example.com",
        subject="Subject",
        body_text="Body",
        payload_json={},
    )

    with pytest.raises(DomainValidationError):
        sink.deliver(email)

    assert sink._build_from_header() == "caseflow@example.com"


def test_worker_entrypoints_cover_retry_cycle_and_loop(monkeypatch) -> None:
    session = SimpleNamespace(closed=False)

    def close_session():
        session.closed = True

    session.close = close_session
    monkeypatch.setattr(document_worker, "get_session_factory", lambda: lambda: session)

    processed_job_ids: list[object] = []

    class FakeDocumentService:
        def __init__(self, session_obj) -> None:
            assert session_obj is session

        def process_document_job(self, *, job_id):
            processed_job_ids.append(job_id)

        def process_due_jobs(self, *, limit):
            return [1, 2][:limit]

    class FakeWebhookService:
        def __init__(self, session_obj) -> None:
            assert session_obj is session

        def process_due_deliveries(self, *, limit):
            return [1][:limit]

    class FakeEmailOutboxService:
        def __init__(self, session_obj) -> None:
            assert session_obj is session

        def process_due_emails(self, *, limit):
            return [1, 2, 3][:limit]

    class FakeAdminNotificationService:
        def __init__(self, session_obj) -> None:
            assert session_obj is session

        def process_due_digests(self, *, limit):
            return min(limit, 4)

    monkeypatch.setattr(document_worker, "DocumentService", FakeDocumentService)
    monkeypatch.setattr(retry_worker, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(retry_worker, "DocumentService", FakeDocumentService)
    monkeypatch.setattr(retry_worker, "WebhookService", FakeWebhookService)
    monkeypatch.setattr(retry_worker, "EmailOutboxService", FakeEmailOutboxService)

    from app.application.services import admin_notifications as admin_notifications_module

    monkeypatch.setattr(
        admin_notifications_module,
        "AdminNotificationService",
        FakeAdminNotificationService,
    )

    job_id = uuid4()
    document_worker.process_document_job(job_id)
    result = retry_worker.run_retry_cycle(limit_per_queue=3)

    assert processed_job_ids == [job_id]
    assert result.processed_document_jobs == 2
    assert result.processed_webhook_deliveries == 1
    assert result.processed_admin_notification_digests == 3
    assert result.processed_emails == 3
    assert session.closed is True

    calls: list[int] = []

    def fake_run_retry_cycle(*, limit_per_queue: int):
        calls.append(limit_per_queue)
        return SimpleNamespace()

    def stop_sleep(seconds: int) -> None:
        raise RuntimeError(f"stop:{seconds}")

    monkeypatch.setattr(retry_worker, "run_retry_cycle", fake_run_retry_cycle)
    monkeypatch.setattr(
        retry_worker,
        "get_settings",
        lambda: SimpleNamespace(worker_poll_interval_seconds=7),
    )
    monkeypatch.setattr(retry_worker.time, "sleep", stop_sleep)

    with pytest.raises(RuntimeError, match="stop:7"):
        retry_worker.run_retry_worker(limit_per_queue=9)

    assert calls == [9]


@pytest.mark.asyncio
async def test_ops_and_assistant_routes_cover_remaining_branches(monkeypatch) -> None:
    monkeypatch.setattr(ops_routes, "database_is_ready", lambda: False)
    response = Response()
    request = build_starlette_request(app=FastAPI())
    request.app.state.settings = SimpleNamespace(app_name="CaseFlow", app_env="test")

    readiness = await ops_routes.readiness(request, response)
    assert response.status_code == 503
    assert readiness["status"] == "degraded"

    now = datetime.now(UTC)
    conversation = SimpleNamespace(
        id=uuid4(),
        case_id=uuid4(),
        title="Thread",
        prompt_mode=AssistantPromptMode.REVIEW_ASSISTANT,
        created_by_user_id=uuid4(),
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    message = SimpleNamespace(
        id=uuid4(),
        conversation_id=conversation.id,
        actor_user_id=uuid4(),
        role=AssistantMessageRole.USER,
        prompt_mode=AssistantPromptMode.REVIEW_ASSISTANT,
        content="Hello",
        citations_json=[],
        metadata_json={},
        created_at=now,
    )

    class FakeAssistantService:
        def __init__(self, session_obj) -> None:
            assert session_obj is session

        def list_conversations(self, **_kwargs):
            return [conversation]

        def list_messages(self, **_kwargs):
            return [message]

    session = object()
    monkeypatch.setattr(assistant_routes, "AssistantService", FakeAssistantService)

    conversations = await assistant_routes.list_assistant_conversations(uuid4(), object(), session)
    messages = await assistant_routes.list_assistant_messages(
        uuid4(),
        conversation.id,
        object(),
        session,
    )

    assert conversations[0].title == "Thread"
    assert messages[0].content == "Hello"


def test_schema_validators_cover_low_level_branches() -> None:
    assert RegistrationRequest(
        organization_name="Acme",
        organization_slug="acme",
        first_name="Ada",
        last_name="Lovelace",
        email=" ADA@example.com ",
        password="StrongPass123",
    ).email == "ada@example.com"

    with pytest.raises(ValidationError):
        LoginRequest(email="invalid", password="secret")

    assert AuthSessionUpdateRequest(device_name=None).device_name is None
    assert AuthSessionUpdateRequest(device_name="  MacBook   Pro ").device_name == "MacBook Pro"

    with pytest.raises(ValidationError):
        PasswordResetConfirmRequest(token="x" * 20, password="lowercaseonly")

    with pytest.raises(ValidationError):
        InvitationCreateRequest(email="not-an-email", role=OrganizationRole.MEMBER)

    with pytest.raises(ValidationError):
        OrganizationMemberUpdateRequest()

    with pytest.raises(ValidationError):
        CaseUpdateRequest()

    with pytest.raises(ValidationError):
        CaseUpdateRequest(status=CaseStatus.ARCHIVED)

    past = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(ValidationError):
        ApiKeyCreateRequest(name="  Demo key  ", scopes=[ApiKeyScope.CASES_READ], expires_at=past)

    assert (
        ApiKeyCreateRequest(
            name="  Demo key  ",
            description="  Useful key  ",
            scopes=[ApiKeyScope.CASES_READ, ApiKeyScope.CASES_READ],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ).scopes
        == [ApiKeyScope.CASES_READ]
    )
    assert api_key_to_utc(datetime.now()).tzinfo == UTC

    with pytest.raises(ValidationError):
        WebhookEndpointCreateRequest(target_url="ftp://bad-target")

    assert WebhookEndpointUpdateRequest(
        target_url=None,
        subscribed_event_types=None,
        is_active=True,
    )

    with pytest.raises(ValidationError):
        WebhookEndpointUpdateRequest()

    with pytest.raises(ValidationError):
        WebhookEndpointCreateRequest(
            target_url="https://hooks.example.com",
            subscribed_event_types=[" ", "x" * 121],
        )
