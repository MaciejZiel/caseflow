"""Schemas for reporting and search responses."""

from __future__ import annotations

from pydantic import BaseModel


class CaseSummaryReportResponse(BaseModel):
    total_cases: int
    active_cases: int
    archived_cases: int
    overdue_cases: int
    due_next_7_days: int
    status_counts: dict[str, int]
    priority_counts: dict[str, int]
