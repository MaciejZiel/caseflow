from __future__ import annotations

import httpx
import pytest

from tests.integration.helpers import (
    create_case,
    encode_document_content,
    register_owner,
    wait_for_document_status,
)


@pytest.mark.asyncio
async def test_owner_can_create_assistant_conversation_and_receive_grounded_answer(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Claim 2048",
    )

    created_document = await async_client.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "title": "Repair estimate",
            "document_type": "invoice",
            "original_filename": "repair-estimate.txt",
            "mime_type": "text/plain",
            "content_base64": encode_document_content(
                b"Unsigned repair estimate for bumper damage.\nAwaiting claimant approval."
            ),
        },
    )
    assert created_document.status_code == 201

    await wait_for_document_status(
        async_client,
        access_token=owner["access_token"],
        document_id=created_document.json()["id"],
        expected_statuses=("ready",),
    )

    conversation = await async_client.post(
        f"/api/v1/cases/{case['id']}/assistant/conversations",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"prompt_mode": "review_assistant"},
    )
    assert conversation.status_code == 201

    asked = await async_client.post(
        f"/api/v1/cases/{case['id']}/assistant/conversations/{conversation.json()['id']}/messages",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "question": "What is missing before we can move this claim forward?",
        },
    )

    assert asked.status_code == 201
    body = asked.json()
    assert body["conversation"]["id"] == conversation.json()["id"]
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert "Claim 2048" in body["assistant_message"]["content"]
    assert "Repair estimate" in body["assistant_message"]["content"]
    assert len(body["assistant_message"]["citations_json"]) == 1
    assert (
        body["assistant_message"]["citations_json"][0]["document_id"]
        == created_document.json()["id"]
    )

    messages = await async_client.get(
        f"/api/v1/cases/{case['id']}/assistant/conversations/{conversation.json()['id']}/messages",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )
    assert messages.status_code == 200
    assert [message["role"] for message in messages.json()] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_assistant_conversations_are_case_scoped(async_client: httpx.AsyncClient) -> None:
    owner = await register_owner(async_client)
    first_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Case one",
    )
    second_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Case two",
    )

    conversation = await async_client.post(
        f"/api/v1/cases/{first_case['id']}/assistant/conversations",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"title": "Scoped thread"},
    )
    assert conversation.status_code == 201

    wrong_scope = await async_client.get(
        f"/api/v1/cases/{second_case['id']}/assistant/conversations/{conversation.json()['id']}/messages",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert wrong_scope.status_code == 404
    assert wrong_scope.json()["error"]["code"] == "assistant_conversation_not_found"
