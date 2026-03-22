from __future__ import annotations

import httpx
import pytest

from tests.integration.helpers import (
    accept_invitation,
    create_case,
    create_invitation,
    encode_document_content,
    register_owner,
    wait_for_document_status,
)


@pytest.mark.asyncio
async def test_owner_can_create_document_and_inspect_versions_and_jobs(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Invoice March 2026",
            "document_type": "invoice",
            "original_filename": "../invoice march.pdf",
            "mime_type": "application/pdf",
            "content_base64": encode_document_content(b"fake-pdf-content"),
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "queued"
    assert body["mime_type"] == "application/pdf"
    assert body["size_bytes"] == len(b"fake-pdf-content")
    assert body["storage_key"].endswith("/invoice_march.pdf")

    fetched = await async_client.get(
        f"/api/v1/documents/{body['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert fetched.status_code == 200
    assert fetched.json()["current_version_id"] is not None

    ready_document = await wait_for_document_status(
        async_client,
        access_token=owner["access_token"],
        document_id=body["id"],
        expected_statuses=("ready",),
    )
    assert ready_document["status"] == "ready"
    assert ready_document["checksum"] is not None

    versions = await async_client.get(
        f"/api/v1/documents/{body['id']}/versions",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert versions.status_code == 200
    assert len(versions.json()) == 1
    assert versions.json()[0]["version_number"] == 1
    assert versions.json()[0]["processing_status"] == "ready"
    assert versions.json()[0]["original_filename"] == "invoice_march.pdf"
    assert versions.json()[0]["extracted_payload_json"]["checksum_sha256"] is not None

    jobs = await async_client.get(
        f"/api/v1/documents/{body['id']}/jobs",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert jobs.status_code == 200
    assert len(jobs.json()) == 1
    assert jobs.json()[0]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_member_can_upload_new_document_version(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Bank statement",
            "document_type": "statement",
            "original_filename": "statement-v1.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"statement-v1"),
        },
    )
    document_id = created.json()["id"]
    first_version_id = created.json()["current_version_id"]

    versioned = await async_client.post(
        f"/api/v1/documents/{document_id}/versions",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Updated bank statement",
            "original_filename": "statement-v2.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"statement-v2"),
        },
    )

    assert versioned.status_code == 201
    assert versioned.json()["title"] == "Updated bank statement"
    assert versioned.json()["current_version_id"] != first_version_id
    assert versioned.json()["status"] == "queued"

    ready_document = await wait_for_document_status(
        async_client,
        access_token=owner["access_token"],
        document_id=document_id,
        expected_statuses=("ready",),
    )
    assert ready_document["status"] == "ready"

    versions = await async_client.get(
        f"/api/v1/documents/{document_id}/versions",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    version_numbers = [item["version_number"] for item in versions.json()]

    assert version_numbers == [1, 2]
    assert versions.json()[1]["processing_status"] == "ready"

    jobs = await async_client.get(
        f"/api/v1/documents/{document_id}/jobs",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert len(jobs.json()) == 2
    assert jobs.json()[0]["status"] == "succeeded"
    assert jobs.json()[1]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_reviewer_can_read_but_cannot_upload_documents(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="reviewer-docs@example.com",
        role="reviewer",
    )
    reviewer = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Rita",
        last_name="Reviewer",
        password="ReviewerPass123",
    )
    reviewer_token = reviewer["body"]["access_token"]

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Contract",
            "document_type": "contract",
            "original_filename": "contract.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"contract-content"),
        },
    )
    document_id = created.json()["id"]

    read_response = await async_client.get(
        f"/api/v1/documents/{document_id}",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    blocked_upload = await async_client.post(
        f"/api/v1/documents/{document_id}/versions",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={
            "original_filename": "contract-v2.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"updated"),
        },
    )

    assert read_response.status_code == 200
    assert blocked_upload.status_code == 403
    assert blocked_upload.json()["error"]["code"] == "permission_denied"


@pytest.mark.asyncio
async def test_document_isolated_between_tenants(async_client: httpx.AsyncClient) -> None:
    owner_one = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner_one["access_token"])
    owner_two_response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other Org",
            "organization_slug": "other-org-docs",
            "first_name": "Second",
            "last_name": "Owner",
            "email": "second-owner-docs@example.com",
            "password": "StrongPass123",
        },
    )
    owner_two_token = owner_two_response.json()["access_token"]

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner_one['access_token']}"},
        json={
            "title": "Tenant one doc",
            "document_type": "other",
            "original_filename": "tenant-one.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"tenant-one"),
        },
    )

    forbidden_read = await async_client.get(
        f"/api/v1/documents/{created.json()['id']}",
        headers={"Authorization": f"Bearer {owner_two_token}"},
    )

    assert forbidden_read.status_code == 404
    assert forbidden_read.json()["error"]["code"] == "document_not_found"


@pytest.mark.asyncio
async def test_reviewer_can_approve_ready_document(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="approval-reviewer@example.com",
        role="reviewer",
    )
    reviewer = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Pola",
        last_name="Approve",
        password="ReviewerPass123",
    )

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Approval target",
            "document_type": "contract",
            "original_filename": "approve.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"ready-to-approve"),
        },
    )
    document_id = created.json()["id"]
    await wait_for_document_status(
        async_client,
        access_token=owner["access_token"],
        document_id=document_id,
        expected_statuses=("ready",),
    )

    approved = await async_client.post(
        f"/api/v1/documents/{document_id}/approve",
        headers={"Authorization": f"Bearer {reviewer['body']['access_token']}"},
        json={"reason": "Looks complete."},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    fetched_case = await async_client.get(
        f"/api/v1/cases/{case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert fetched_case.status_code == 200
    assert fetched_case.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_reviewer_can_reject_ready_document(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="reject-reviewer@example.com",
        role="reviewer",
    )
    reviewer = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Rafal",
        last_name="Reject",
        password="ReviewerPass123",
    )

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Reject target",
            "document_type": "id_document",
            "original_filename": "reject.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"ready-to-reject"),
        },
    )
    document_id = created.json()["id"]
    await wait_for_document_status(
        async_client,
        access_token=owner["access_token"],
        document_id=document_id,
        expected_statuses=("ready",),
    )

    rejected = await async_client.post(
        f"/api/v1/documents/{document_id}/reject",
        headers={"Authorization": f"Bearer {reviewer['body']['access_token']}"},
        json={"reason": "Missing required data."},
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    fetched_case = await async_client.get(
        f"/api/v1/cases/{case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert fetched_case.status_code == 200
    assert fetched_case.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_failed_processing_job_can_be_retried_manually(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(async_client, access_token=owner["access_token"])

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Broken payload",
            "document_type": "other",
            "original_filename": "broken.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"FAIL_PROCESSING: invalid payload"),
        },
    )

    assert created.status_code == 201
    document_id = created.json()["id"]

    jobs = await async_client.get(
        f"/api/v1/documents/{document_id}/jobs",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert jobs.status_code == 200
    assert jobs.json()[0]["status"] == "failed"
    assert jobs.json()[0]["attempts"] == 1

    retried = await async_client.post(
        f"/api/v1/documents/{document_id}/jobs/{jobs.json()[0]['id']}/retry",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert retried.status_code == 200
    assert retried.json()["status"] == "failed"
    assert retried.json()["attempts"] == 2
    assert retried.json()["last_error"] is not None
