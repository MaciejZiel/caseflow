from __future__ import annotations

import httpx
import pytest

from tests.integration.helpers import (
    accept_invitation,
    create_case,
    create_invitation,
    register_owner,
)


@pytest.mark.asyncio
async def test_member_can_create_and_list_case_comments(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Commentable case",
    )

    comment = await async_client.post(
        f"/api/v1/cases/{case['id']}/comments",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"body": "Need one more attachment before final approval."},
    )

    assert comment.status_code == 201
    assert comment.json()["body"] == "Need one more attachment before final approval."

    listed = await async_client.get(
        f"/api/v1/cases/{case['id']}/comments",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == comment.json()["id"]

    audit_log = await async_client.get(
        f"/api/v1/cases/{case['id']}/audit-log",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert audit_log.status_code == 200
    assert [item["event_type"] for item in audit_log.json()] == [
        "case.created",
        "case.comment_created",
    ]


@pytest.mark.asyncio
async def test_reviewer_can_comment_but_cross_tenant_cannot_read(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Reviewer case",
    )
    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="review-commenter@example.com",
        role="reviewer",
    )
    reviewer = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Rita",
        last_name="Commenter",
        password="ReviewerPass123",
    )
    other_owner_response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other Org",
            "organization_slug": "other-org-comments",
            "first_name": "Second",
            "last_name": "Owner",
            "email": "other-owner-comments@example.com",
            "password": "StrongPass123",
        },
    )
    other_owner_token = other_owner_response.json()["access_token"]

    created = await async_client.post(
        f"/api/v1/cases/{case['id']}/comments",
        headers={"Authorization": f"Bearer {reviewer['body']['access_token']}"},
        json={"body": "Reviewer note for the file."},
    )

    assert created.status_code == 201

    forbidden = await async_client.get(
        f"/api/v1/cases/{case['id']}/comments",
        headers={"Authorization": f"Bearer {other_owner_token}"},
    )

    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "case_not_found"
