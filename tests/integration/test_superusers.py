from __future__ import annotations

import httpx
import pytest

from app.application.services.superusers import SuperuserService
from app.infrastructure.db.session import get_session_factory
from tests.integration.helpers import register_owner


@pytest.mark.asyncio
async def test_superuser_service_promotes_and_demotes_platform_access(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(
        async_client,
        organization_name="Platform Admins",
        organization_slug="platform-admins",
        email="root@example.com",
    )

    session = get_session_factory()()
    try:
        promoted_user = SuperuserService(session).set_superuser_status(
            email=owner["email"],
            is_superuser=True,
        )
        assert promoted_user.is_superuser is True
    finally:
        session.close()

    overview = await async_client.get(
        "/api/v1/admin/overview",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert overview.status_code == 200

    session = get_session_factory()()
    try:
        demoted_user = SuperuserService(session).set_superuser_status(
            email=owner["email"],
            is_superuser=False,
        )
        assert demoted_user.is_superuser is False
    finally:
        session.close()

    forbidden = await async_client.get(
        "/api/v1/admin/overview",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert forbidden.status_code == 403
