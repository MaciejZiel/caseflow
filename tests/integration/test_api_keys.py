from __future__ import annotations

import httpx
import pytest

from tests.integration.helpers import create_case, encode_document_content, register_owner


async def create_api_key(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    scopes: list[str],
    name: str = "Primary integration key",
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name, "scopes": scopes},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_owner_can_create_list_and_revoke_api_keys(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    created = await create_api_key(
        async_client,
        access_token=owner["access_token"],
        scopes=["cases:read", "documents:read"],
    )

    assert created["plaintext_key"].startswith("cfk_")
    assert created["scopes"] == ["cases:read", "documents:read"]
    assert created["revoked_at"] is None

    listed = await async_client.get(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert listed.status_code == 200
    listed_body = listed.json()
    assert len(listed_body) == 1
    assert listed_body[0]["key_prefix"] == created["key_prefix"]
    assert "plaintext_key" not in listed_body[0]

    revoked = await async_client.post(
        f"/api/v1/api-keys/{created['id']}/revoke",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert revoked.json()["revoke_reason"] == "manual_revoke"


@pytest.mark.asyncio
async def test_api_key_can_read_tenant_scoped_cases_and_documents(
    async_client: httpx.AsyncClient,
) -> None:
    owner_one = await register_owner(async_client)
    owner_two_response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other Org",
            "organization_slug": "other-org-api-keys",
            "first_name": "Second",
            "last_name": "Owner",
            "email": "second-owner-api-keys@example.com",
            "password": "StrongPass123",
        },
    )
    owner_two_token = owner_two_response.json()["access_token"]

    case = await create_case(
        async_client,
        access_token=owner_one["access_token"],
        title="API key visible case",
    )
    await create_case(
        async_client,
        access_token=owner_two_token,
        title="Other tenant hidden case",
    )
    document = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner_one['access_token']}"},
        json={
            "title": "Integration payload",
            "document_type": "attachment",
            "original_filename": "integration.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"integration payload"),
        },
    )
    document_body = document.json()

    created_key = await create_api_key(
        async_client,
        access_token=owner_one["access_token"],
        scopes=["cases:read", "documents:read"],
    )
    integration_headers = {"X-API-Key": created_key["plaintext_key"]}

    listed_cases = await async_client.get("/api/v1/integrations/cases", headers=integration_headers)
    assert listed_cases.status_code == 200
    assert [item["id"] for item in listed_cases.json()] == [case["id"]]

    fetched_case = await async_client.get(
        f"/api/v1/integrations/cases/{case['id']}",
        headers=integration_headers,
    )
    assert fetched_case.status_code == 200
    assert fetched_case.json()["title"] == "API key visible case"

    listed_documents = await async_client.get(
        f"/api/v1/integrations/cases/{case['id']}/documents",
        headers=integration_headers,
    )
    assert listed_documents.status_code == 200
    assert [item["id"] for item in listed_documents.json()] == [document_body["id"]]

    fetched_document = await async_client.get(
        f"/api/v1/integrations/documents/{document_body['id']}",
        headers=integration_headers,
    )
    assert fetched_document.status_code == 200
    assert fetched_document.json()["title"] == "Integration payload"


@pytest.mark.asyncio
async def test_api_key_scope_restrictions_are_enforced(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])
    document = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Scope-limited document",
            "document_type": "attachment",
            "original_filename": "scope.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"scope"),
        },
    )
    document_id = document.json()["id"]

    created_key = await create_api_key(
        async_client,
        access_token=owner["access_token"],
        scopes=["cases:read"],
    )

    allowed_case_request = await async_client.get(
        f"/api/v1/integrations/cases/{case['id']}",
        headers={"X-API-Key": created_key["plaintext_key"]},
    )
    denied_document_request = await async_client.get(
        f"/api/v1/integrations/documents/{document_id}",
        headers={"X-API-Key": created_key["plaintext_key"]},
    )

    assert allowed_case_request.status_code == 200
    assert denied_document_request.status_code == 403
    assert denied_document_request.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_revoked_api_key_is_rejected_by_integration_endpoints(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])
    created_key = await create_api_key(
        async_client,
        access_token=owner["access_token"],
        scopes=["cases:read"],
    )

    revoke_response = await async_client.post(
        f"/api/v1/api-keys/{created_key['id']}/revoke",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert revoke_response.status_code == 200

    integration_response = await async_client.get(
        f"/api/v1/integrations/cases/{case['id']}",
        headers={"X-API-Key": created_key["plaintext_key"]},
    )

    assert integration_response.status_code == 401
