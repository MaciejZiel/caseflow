from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence
from contextlib import asynccontextmanager

import httpx

from app.application.services.superusers import SuperuserService
from app.core.config import get_settings
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import import_model_modules
from app.infrastructure.db.session import get_engine, get_session_factory, reset_db_state
from app.main import create_app


def registration_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "organization_name": "Acme Claims",
        "organization_slug": "acme-claims",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "password": "StrongPass123",
    }
    payload.update(overrides)
    return payload


async def register_owner(
    async_client: httpx.AsyncClient,
    **overrides: str,
) -> dict[str, str]:
    response = await async_client.post(
        "/api/v1/auth/register",
        json=registration_payload(**overrides),
    )
    body = response.json()
    return {
        "access_token": body["access_token"],
        "refresh_token": body["refresh_token"],
        "user_id": body["user"]["id"],
        "email": body["user"]["email"],
        "organization_slug": body["organization"]["slug"],
        "organization_id": body["organization"]["id"],
    }


async def create_case(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    title: str = "Primary case",
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"title": title},
    )
    return response.json()


async def create_invitation(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    email: str,
    role: str,
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"email": email, "role": role},
    )
    return response.json()


async def accept_invitation(
    async_client: httpx.AsyncClient,
    *,
    token: str,
    first_name: str,
    last_name: str,
    password: str,
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "first_name": first_name,
            "last_name": last_name,
            "password": password,
        },
    )
    return {
        "status_code": response.status_code,
        "body": response.json(),
    }


def promote_user_to_superuser(*, email: str) -> None:
    session = get_session_factory()()
    try:
        SuperuserService(session).set_superuser_status(
            email=email,
            is_superuser=True,
        )
    finally:
        session.close()


def encode_document_content(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


@asynccontextmanager
async def configured_async_client(
    tmp_path,
    monkeypatch,
    *,
    env_overrides: dict[str, str] | None = None,
):
    database_path = tmp_path / "caseflow-configured-test.db"
    env_values = {
        "DATABASE_URL": f"sqlite+pysqlite:///{database_path}",
        "TEST_DATABASE_URL": f"sqlite+pysqlite:///{database_path}",
        "SECRET_KEY": "test-secret-key-with-32-plus-bytes",
        "LOCAL_STORAGE_PATH": str(tmp_path / "storage"),
        "LOCAL_EMAIL_SINK_PATH": str(tmp_path / "emails"),
    }
    if env_overrides:
        env_values.update(env_overrides)
    for key, value in env_values.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    reset_db_state()
    import_model_modules()

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    reset_db_state()
    get_settings.cache_clear()


async def wait_for_document_status(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    document_id: str,
    expected_statuses: Sequence[str],
    attempts: int = 5,
) -> dict[str, object]:
    response_body: dict[str, object] = {}
    for _ in range(attempts):
        response = await async_client.get(
            f"/api/v1/documents/{document_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response_body = response.json()
        if response_body["status"] in expected_statuses:
            return response_body
        await asyncio.sleep(0.02)
    return response_body
