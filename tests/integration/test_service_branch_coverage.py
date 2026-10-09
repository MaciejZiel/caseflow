from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.domain.api_keys.models import ApiKey
from app.domain.cases.models import Case
from app.domain.organizations.models import Organization, OrganizationStatus
from app.infrastructure.db.session import get_session_factory
from tests.integration.helpers import (
    accept_invitation,
    create_case,
    create_invitation,
    encode_document_content,
    register_owner,
    wait_for_document_status,
)


async def _create_api_key(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    scopes: list[str],
    name: str = "Coverage integration key",
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": name, "scopes": scopes},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_organization_member_update_guardrails_cover_owner_edge_cases(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)

    second_owner_invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="second-owner@example.com",
        role="owner",
    )
    second_owner = await accept_invitation(
        async_client,
        token=str(second_owner_invitation["invitation_token"]),
        first_name="Second",
        last_name="Owner",
        password="SecondOwnerPass123",
    )
    second_owner_membership_id = second_owner["body"]["membership"]["id"]

    admin_invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="org-admin@example.com",
        role="admin",
    )
    admin = await accept_invitation(
        async_client,
        token=str(admin_invitation["invitation_token"]),
        first_name="Org",
        last_name="Admin",
        password="AdminPass123",
    )

    owner_members = await async_client.get(
        "/api/v1/organizations/current/members",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert owner_members.status_code == 200
    owner_membership_id = next(
        member["id"]
        for member in owner_members.json()
        if member["user"]["email"] == owner["email"]
    )

    admin_modifies_owner = await async_client.patch(
        f"/api/v1/organizations/current/members/{owner_membership_id}",
        headers={"Authorization": f"Bearer {admin['body']['access_token']}"},
        json={"role": "admin"},
    )
    assert admin_modifies_owner.status_code == 400
    assert admin_modifies_owner.json()["error"]["code"] == "owner_member_update_forbidden"

    self_deactivate = await async_client.patch(
        f"/api/v1/organizations/current/members/{owner_membership_id}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"is_active": False},
    )
    assert self_deactivate.status_code == 400
    assert self_deactivate.json()["error"]["code"] == "self_deactivation_forbidden"

    self_role_change = await async_client.patch(
        f"/api/v1/organizations/current/members/{owner_membership_id}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"role": "admin"},
    )
    assert self_role_change.status_code == 400
    assert self_role_change.json()["error"]["code"] == "self_role_change_forbidden"

    deactivate_second_owner = await async_client.patch(
        f"/api/v1/organizations/current/members/{second_owner_membership_id}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"is_active": False},
    )
    assert deactivate_second_owner.status_code == 200

    last_owner_deactivation = await async_client.patch(
        f"/api/v1/organizations/current/members/{second_owner_membership_id}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"is_active": False},
    )
    assert last_owner_deactivation.status_code == 400
    assert last_owner_deactivation.json()["error"]["code"] == "last_owner_deactivation_forbidden"

    last_owner_demotion = await async_client.patch(
        f"/api/v1/organizations/current/members/{second_owner_membership_id}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"role": "reviewer"},
    )
    assert last_owner_demotion.status_code == 400
    assert last_owner_demotion.json()["error"]["code"] == "last_owner_demotion_forbidden"


@pytest.mark.asyncio
async def test_member_update_and_invitations_reject_unknown_duplicate_and_conflicting_targets(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)

    missing_member = await async_client.patch(
        f"/api/v1/organizations/current/members/{uuid4()}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"role": "reviewer"},
    )
    assert missing_member.status_code == 404
    assert missing_member.json()["error"]["code"] == "organization_member_not_found"

    admin_invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="admin@example.com",
        role="admin",
    )
    admin = await accept_invitation(
        async_client,
        token=str(admin_invitation["invitation_token"]),
        first_name="Invite",
        last_name="Admin",
        password="AdminPass123",
    )

    owner_invite_by_admin = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {admin['body']['access_token']}"},
        json={"email": "new-owner@example.com", "role": "owner"},
    )
    assert owner_invite_by_admin.status_code == 400
    assert owner_invite_by_admin.json()["error"]["code"] == "owner_invitation_forbidden"

    invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email="member@example.com",
        role="member",
    )
    duplicate_pending = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"email": "member@example.com", "role": "member"},
    )
    assert duplicate_pending.status_code == 409
    assert duplicate_pending.json()["error"]["code"] == "invitation_already_pending"

    accepted = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Covered",
        last_name="Member",
        password="MemberPass123",
    )
    assert accepted["status_code"] == 201

    duplicate_member = await async_client.post(
        "/api/v1/organizations/current/invitations",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"email": "member@example.com", "role": "reviewer"},
    )
    assert duplicate_member.status_code == 409
    assert duplicate_member.json()["error"]["code"] == "member_already_exists"

    reused_accept = await accept_invitation(
        async_client,
        token=str(invitation["invitation_token"]),
        first_name="Covered",
        last_name="Member",
        password="MemberPass123",
    )
    assert reused_accept["status_code"] == 400
    assert reused_accept["body"]["error"]["code"] == "invitation_already_accepted"

    invalid_accept = await accept_invitation(
        async_client,
        token="definitely-invalid-token",
        first_name="Invalid",
        last_name="Invite",
        password="InvalidPass123",
    )
    assert invalid_accept["status_code"] == 400
    assert invalid_accept["body"]["error"]["code"] == "invalid_invitation_token"


@pytest.mark.asyncio
async def test_invitation_accept_rejects_inactive_organization_and_existing_user(
    async_client: httpx.AsyncClient,
) -> None:
    inactive_owner = await register_owner(
        async_client,
        organization_name="Inactive Org",
        organization_slug="inactive-org",
        email="inactive-owner@example.com",
    )
    inactive_invitation = await create_invitation(
        async_client,
        access_token=inactive_owner["access_token"],
        email="inactive-member@example.com",
        role="member",
    )

    session = get_session_factory()()
    try:
        organization = session.scalar(
            select(Organization).where(Organization.id == UUID(inactive_owner["organization_id"]))
        )
        assert organization is not None
        organization.status = OrganizationStatus.SUSPENDED
        session.commit()
    finally:
        session.close()

    inactive_accept = await accept_invitation(
        async_client,
        token=str(inactive_invitation["invitation_token"]),
        first_name="Inactive",
        last_name="Member",
        password="InactivePass123",
    )
    assert inactive_accept["status_code"] == 400
    assert inactive_accept["body"]["error"]["code"] == "organization_inactive"

    owner = await register_owner(
        async_client,
        organization_name="Conflict Org",
        organization_slug="conflict-org",
        email="conflict-owner@example.com",
    )
    existing_user = await register_owner(
        async_client,
        organization_name="Existing User Org",
        organization_slug="existing-user-org",
        email="existing-user@example.com",
    )
    conflicting_invitation = await create_invitation(
        async_client,
        access_token=owner["access_token"],
        email=existing_user["email"],
        role="reviewer",
    )

    conflicting_accept = await accept_invitation(
        async_client,
        token=str(conflicting_invitation["invitation_token"]),
        first_name="Existing",
        last_name="User",
        password="ExistingPass123",
    )
    assert conflicting_accept["status_code"] == 409
    assert conflicting_accept["body"]["error"]["code"] == "email_already_in_use"


@pytest.mark.asyncio
async def test_case_filters_and_archival_guards_cover_remaining_case_service_branches(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)

    filtered_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Filtered case",
    )
    other_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Other case",
    )

    filtered_update = await async_client.patch(
        f"/api/v1/cases/{filtered_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "status": "in_review",
            "priority": "high",
            "external_id": "FILTER-001",
        },
    )
    other_update = await async_client.patch(
        f"/api/v1/cases/{other_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"status": "rejected", "priority": "low"},
    )
    assert filtered_update.status_code == 200
    assert other_update.status_code == 200

    filtered_list = await async_client.get(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"status": "in_review", "priority": "high"},
    )
    assert filtered_list.status_code == 200
    assert [item["id"] for item in filtered_list.json()] == [filtered_case["id"]]

    invalid_owner_create = await async_client.post(
        "/api/v1/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"title": "Invalid owner case", "owner_user_id": str(uuid4())},
    )
    assert invalid_owner_create.status_code == 400
    assert invalid_owner_create.json()["error"]["code"] == "invalid_case_owner"

    invalid_owner_update = await async_client.patch(
        f"/api/v1/cases/{filtered_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"owner_user_id": str(uuid4())},
    )
    assert invalid_owner_update.status_code == 400
    assert invalid_owner_update.json()["error"]["code"] == "invalid_case_owner"

    missing_update = await async_client.patch(
        f"/api/v1/cases/{uuid4()}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"status": "in_review"},
    )
    assert missing_update.status_code == 404
    assert missing_update.json()["error"]["code"] == "case_not_found"

    archived = await async_client.post(
        f"/api/v1/cases/{filtered_case['id']}/archive",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert archived.status_code == 200

    archived_update = await async_client.patch(
        f"/api/v1/cases/{filtered_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"title": "Still archived"},
    )
    assert archived_update.status_code == 400
    assert archived_update.json()["error"]["code"] == "archived_case_update_forbidden"

    archived_comment = await async_client.post(
        f"/api/v1/cases/{filtered_case['id']}/comments",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"body": "Cannot comment"},
    )
    assert archived_comment.status_code == 400
    assert archived_comment.json()["error"]["code"] == "archived_case_comment_forbidden"

    second_archive = await async_client.post(
        f"/api/v1/cases/{filtered_case['id']}/archive",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert second_archive.status_code == 400
    assert second_archive.json()["error"]["code"] == "case_already_archived"

    missing_archive = await async_client.post(
        f"/api/v1/cases/{uuid4()}/archive",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert missing_archive.status_code == 404
    assert missing_archive.json()["error"]["code"] == "case_not_found"


@pytest.mark.asyncio
async def test_api_key_filters_and_state_guards_cover_remaining_integration_branches(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)

    selected_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Selected integration case",
    )
    other_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Excluded integration case",
    )
    case_document = await async_client.post(
        f"/api/v1/cases/{selected_case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Integration document",
            "document_type": "attachment",
            "original_filename": "integration.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"integration-ready"),
        },
    )
    assert case_document.status_code == 201

    selected_update = await async_client.patch(
        f"/api/v1/cases/{selected_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"status": "in_review", "external_id": "API-FILTER-001"},
    )
    assert selected_update.status_code == 200

    session = get_session_factory()()
    try:
        stale_case = session.scalar(select(Case).where(Case.id == UUID(other_case["id"])))
        assert stale_case is not None
        stale_case.updated_at = datetime.now(UTC) - timedelta(days=3)
        session.commit()
    finally:
        session.close()

    api_key = await _create_api_key(
        async_client,
        access_token=owner["access_token"],
        scopes=["cases:read", "documents:read"],
    )
    headers = {"X-API-Key": api_key["plaintext_key"]}

    filtered_cases = await async_client.get(
        "/api/v1/integrations/cases",
        headers=headers,
        params={
            "status": "in_review",
            "external_id": "API-FILTER-001",
            "updated_after": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        },
    )
    assert filtered_cases.status_code == 200
    assert [item["id"] for item in filtered_cases.json()] == [selected_case["id"]]

    missing_case = await async_client.get(
        f"/api/v1/integrations/cases/{uuid4()}",
        headers=headers,
    )
    assert missing_case.status_code == 404
    assert missing_case.json()["error"]["code"] == "case_not_found"

    missing_document = await async_client.get(
        f"/api/v1/integrations/documents/{uuid4()}",
        headers=headers,
    )
    assert missing_document.status_code == 404
    assert missing_document.json()["error"]["code"] == "document_not_found"

    unknown_api_key = await async_client.get(
        "/api/v1/integrations/cases",
        headers={"X-API-Key": "cfk_unknown"},
    )
    assert unknown_api_key.status_code == 401

    missing_revoke = await async_client.post(
        f"/api/v1/api-keys/{uuid4()}/revoke",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert missing_revoke.status_code == 404
    assert missing_revoke.json()["error"]["code"] == "api_key_not_found"

    expired_key = await _create_api_key(
        async_client,
        access_token=owner["access_token"],
        scopes=["cases:read"],
        name="Expired key",
    )
    session = get_session_factory()()
    try:
        expired_record = session.scalar(select(ApiKey).where(ApiKey.id == UUID(expired_key["id"])))
        assert expired_record is not None
        expired_record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    finally:
        session.close()

    expired_response = await async_client.get(
        "/api/v1/integrations/cases",
        headers={"X-API-Key": expired_key["plaintext_key"]},
    )
    assert expired_response.status_code == 401

    suspended_key = await _create_api_key(
        async_client,
        access_token=owner["access_token"],
        scopes=["cases:read"],
        name="Suspended org key",
    )
    session = get_session_factory()()
    try:
        organization = session.scalar(
            select(Organization).where(Organization.id == UUID(owner["organization_id"]))
        )
        assert organization is not None
        organization.status = OrganizationStatus.SUSPENDED
        session.commit()
    finally:
        session.close()

    suspended_response = await async_client.get(
        "/api/v1/integrations/cases",
        headers={"X-API-Key": suspended_key["plaintext_key"]},
    )
    assert suspended_response.status_code == 401


@pytest.mark.asyncio
async def test_assistant_covers_empty_archived_and_failed_document_paths(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)

    archived_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Archived assistant case",
    )
    due_date = datetime(2030, 1, 15, 12, 0, tzinfo=UTC).isoformat()
    dated_case = await async_client.patch(
        f"/api/v1/cases/{archived_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"due_date": due_date},
    )
    assert dated_case.status_code == 200

    archived_response = await async_client.post(
        f"/api/v1/cases/{archived_case['id']}/archive",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert archived_response.status_code == 200

    empty_conversation = await async_client.post(
        f"/api/v1/cases/{archived_case['id']}/assistant/conversations",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"title": "   ", "prompt_mode": "next_actions"},
    )
    assert empty_conversation.status_code == 201
    assert empty_conversation.json()["title"] == "Archived assistant case assistant"

    empty_exchange = await async_client.post(
        (
            f"/api/v1/cases/{archived_case['id']}/assistant/conversations/"
            f"{empty_conversation.json()['id']}/messages"
        ),
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"question": "???"},
    )
    assert empty_exchange.status_code == 201
    empty_body = empty_exchange.json()
    assert empty_body["conversation"]["title"] == "???"
    assert empty_body["assistant_message"]["citations_json"] == []
    assert "Due date: 2030-01-15." in empty_body["assistant_message"]["content"]
    assert (
        "No documents are attached to this case yet"
        in empty_body["assistant_message"]["content"]
    )
    assert "The case is archived" in empty_body["assistant_message"]["content"]

    failed_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Failed document assistant case",
    )
    failed_document = await async_client.post(
        f"/api/v1/cases/{failed_case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Broken intake package",
            "document_type": "attachment",
            "original_filename": "broken.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(b"FAIL_PROCESSING broken payload"),
        },
    )
    assert failed_document.status_code == 201
    failed_document_id = failed_document.json()["id"]

    failed_status = await wait_for_document_status(
        async_client,
        access_token=owner["access_token"],
        document_id=failed_document_id,
        expected_statuses=("failed",),
    )
    assert failed_status["status"] == "failed"

    failed_conversation = await async_client.post(
        f"/api/v1/cases/{failed_case['id']}/assistant/conversations",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"prompt_mode": "review_assistant"},
    )
    assert failed_conversation.status_code == 201

    failed_exchange = await async_client.post(
        (
            f"/api/v1/cases/{failed_case['id']}/assistant/conversations/"
            f"{failed_conversation.json()['id']}/messages"
        ),
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"question": "What is broken and what needs attention?"},
    )
    assert failed_exchange.status_code == 201
    failed_body = failed_exchange.json()
    assert failed_body["assistant_message"]["citations_json"][0]["document_status"] == "failed"
    assert "needs attention" in failed_body["assistant_message"]["content"].lower()
