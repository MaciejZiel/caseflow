from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tests.integration.helpers import create_case, register_owner


async def create_api_key(
    async_client: httpx.AsyncClient,
    *,
    access_token: str,
    scopes: list[str],
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"name": "Reporting key", "scopes": scopes},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_case_summary_report_aggregates_statuses_and_due_dates(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    first_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="First case",
    )
    second_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Archived case",
    )

    overdue_due_date = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    due_soon = (datetime.now(UTC) + timedelta(days=3)).isoformat()

    overdue_update = await async_client.patch(
        f"/api/v1/cases/{first_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "status": "in_review",
            "priority": "high",
            "external_id": "CASE-OVERDUE",
            "due_date": overdue_due_date,
        },
    )
    due_soon_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Due soon case",
    )
    due_soon_update = await async_client.patch(
        f"/api/v1/cases/{due_soon_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={"due_date": due_soon},
    )
    archived_response = await async_client.post(
        f"/api/v1/cases/{second_case['id']}/archive",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert overdue_update.status_code == 200
    assert due_soon_update.status_code == 200
    assert archived_response.status_code == 200

    summary = await async_client.get(
        "/api/v1/reports/cases/summary",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
    )

    assert summary.status_code == 200
    body = summary.json()
    assert body["total_cases"] == 3
    assert body["active_cases"] == 2
    assert body["archived_cases"] == 1
    assert body["overdue_cases"] == 1
    assert body["due_next_7_days"] == 1
    assert body["status_counts"]["in_review"] == 1
    assert body["status_counts"]["archived"] == 1
    assert body["priority_counts"]["high"] == 1


@pytest.mark.asyncio
async def test_case_search_matches_title_description_and_external_id(
    async_client: httpx.AsyncClient,
) -> None:
    owner = await register_owner(async_client)
    invoice_case = await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Invoice dispute March",
    )
    await async_client.patch(
        f"/api/v1/cases/{invoice_case['id']}",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        json={
            "description": "Waiting for bank statement review",
            "external_id": "INV-2026-03",
        },
    )
    await create_case(
        async_client,
        access_token=owner["access_token"],
        title="Contract renewal",
    )

    title_search = await async_client.get(
        "/api/v1/search/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"q": "invoice"},
    )
    external_id_search = await async_client.get(
        "/api/v1/search/cases",
        headers={"Authorization": f"Bearer {owner['access_token']}"},
        params={"q": "INV-2026-03"},
    )

    assert title_search.status_code == 200
    assert [item["id"] for item in title_search.json()] == [invoice_case["id"]]
    assert external_id_search.status_code == 200
    assert [item["id"] for item in external_id_search.json()] == [invoice_case["id"]]


@pytest.mark.asyncio
async def test_integration_case_export_returns_tenant_scoped_csv(
    async_client: httpx.AsyncClient,
) -> None:
    owner_one = await register_owner(async_client)
    owner_two_response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other Export Org",
            "organization_slug": "other-export-org",
            "first_name": "Second",
            "last_name": "Owner",
            "email": "second-owner-export@example.com",
            "password": "StrongPass123",
        },
    )
    owner_two_token = owner_two_response.json()["access_token"]

    visible_case = await create_case(
        async_client,
        access_token=owner_one["access_token"],
        title="Visible export case",
    )
    await async_client.patch(
        f"/api/v1/cases/{visible_case['id']}",
        headers={"Authorization": f"Bearer {owner_one['access_token']}"},
        json={"external_id": "EXPORT-001"},
    )
    await create_case(
        async_client,
        access_token=owner_two_token,
        title="Hidden export case",
    )
    api_key = await create_api_key(
        async_client,
        access_token=owner_one["access_token"],
        scopes=["cases:read"],
    )

    exported = await async_client.get(
        "/api/v1/integrations/exports/cases.csv",
        headers={"X-API-Key": api_key["plaintext_key"]},
    )

    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"cases-export.csv\"" == exported.headers["content-disposition"]
    assert "Visible export case" in exported.text
    assert "EXPORT-001" in exported.text
    assert "Hidden export case" not in exported.text
