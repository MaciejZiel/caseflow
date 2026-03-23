"""Platform admin review workflow routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import SuperuserActor, get_current_superuser_actor
from app.api.v1.schemas.admin_reviews import (
    AdminReviewAttentionResponse,
    AdminReviewAutoAssignPreviewItemResponse,
    AdminReviewAutoAssignRequest,
    AdminReviewAutoAssignResponse,
    AdminReviewAutoAssignResultItemResponse,
    AdminReviewAutoOpenPreviewItemResponse,
    AdminReviewAutoOpenRequest,
    AdminReviewAutoOpenResponse,
    AdminReviewAutoOpenResultItemResponse,
    AdminReviewCommentCreateRequest,
    AdminReviewCommentResponse,
    AdminReviewCreateRequest,
    AdminReviewDetailResponse,
    AdminReviewEscalateOverdueRequest,
    AdminReviewEscalateOverdueResponse,
    AdminReviewEscalationPreviewItemResponse,
    AdminReviewEscalationResultItemResponse,
    AdminReviewOrganizationResponse,
    AdminReviewResponse,
    AdminReviewSummaryResponse,
    AdminReviewUpdateRequest,
    AdminReviewUserResponse,
    AdminReviewWorkloadResponse,
)
from app.application.services.admin_reviews import (
    AdminReviewAttentionItem,
    AdminReviewAutoAssignPreviewItem,
    AdminReviewAutoAssignResult,
    AdminReviewAutoAssignResultItem,
    AdminReviewAutoOpenCandidate,
    AdminReviewAutoOpenResult,
    AdminReviewAutoOpenResultItem,
    AdminReviewCommentItem,
    AdminReviewDetail,
    AdminReviewEscalateOverdueResult,
    AdminReviewEscalationPreviewItem,
    AdminReviewEscalationResultItem,
    AdminReviewListItem,
    AdminReviewService,
    AdminReviewSummary,
    AdminReviewUserRef,
    AdminReviewWorkloadItem,
)
from app.domain.admin_reviews.models import AdminReviewPriority, AdminReviewStatus
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/admin")
SessionDep = Annotated[Session, Depends(get_db_session)]
SuperuserActorDep = Annotated[SuperuserActor, Depends(get_current_superuser_actor)]
LIMIT_QUERY = Query(default=50, ge=1, le=200)


@router.get("/reviews/summary", response_model=AdminReviewSummaryResponse)
async def get_review_summary(
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewSummaryResponse:
    summary = AdminReviewService(session).get_review_summary(actor=actor)
    return _to_review_summary_response(summary)


@router.get("/reviews/workload", response_model=list[AdminReviewWorkloadResponse])
async def list_review_workload(
    actor: SuperuserActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[AdminReviewWorkloadResponse]:
    workload = AdminReviewService(session).list_review_workload(
        actor=actor,
        limit=limit,
    )
    return [_to_review_workload_response(item) for item in workload]


@router.get("/reviews/attention-queue", response_model=list[AdminReviewAttentionResponse])
async def list_attention_queue(
    actor: SuperuserActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[AdminReviewAttentionResponse]:
    attention_items = AdminReviewService(session).list_attention_queue(
        actor=actor,
        limit=limit,
    )
    return [_to_review_attention_response(item) for item in attention_items]


@router.get(
    "/reviews/auto-assign-preview",
    response_model=list[AdminReviewAutoAssignPreviewItemResponse],
)
async def preview_auto_assign_reviews(
    actor: SuperuserActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[AdminReviewAutoAssignPreviewItemResponse]:
    preview_items = AdminReviewService(session).preview_auto_assignments(
        actor=actor,
        limit=limit,
    )
    return [_to_auto_assign_preview_response(item) for item in preview_items]


@router.post("/reviews/auto-assign", response_model=AdminReviewAutoAssignResponse)
async def auto_assign_reviews(
    payload: AdminReviewAutoAssignRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewAutoAssignResponse:
    result = AdminReviewService(session).auto_assign_reviews(
        actor=actor,
        payload=payload,
    )
    return _to_auto_assign_response(result)


@router.get(
    "/reviews/auto-open-preview",
    response_model=list[AdminReviewAutoOpenPreviewItemResponse],
)
async def preview_auto_open_reviews(
    actor: SuperuserActorDep,
    session: SessionDep,
    min_risk_score: Annotated[int, Query(ge=1, le=1_000)] = 50,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[AdminReviewAutoOpenPreviewItemResponse]:
    candidates = AdminReviewService(session).preview_auto_open_candidates(
        actor=actor,
        min_risk_score=min_risk_score,
        limit=limit,
    )
    return [_to_auto_open_preview_response(item) for item in candidates]


@router.post("/reviews/auto-open", response_model=AdminReviewAutoOpenResponse)
async def auto_open_reviews(
    payload: AdminReviewAutoOpenRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewAutoOpenResponse:
    result = AdminReviewService(session).auto_open_reviews(actor=actor, payload=payload)
    return _to_auto_open_response(result)


@router.get(
    "/reviews/escalation-preview",
    response_model=list[AdminReviewEscalationPreviewItemResponse],
)
async def preview_overdue_review_escalations(
    actor: SuperuserActorDep,
    session: SessionDep,
    min_days_overdue: Annotated[int, Query(ge=1, le=365)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[AdminReviewEscalationPreviewItemResponse]:
    previews = AdminReviewService(session).preview_overdue_escalations(
        actor=actor,
        min_days_overdue=min_days_overdue,
        limit=limit,
    )
    return [_to_escalation_preview_response(item) for item in previews]


@router.post("/reviews/escalate-overdue", response_model=AdminReviewEscalateOverdueResponse)
async def escalate_overdue_reviews(
    payload: AdminReviewEscalateOverdueRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewEscalateOverdueResponse:
    result = AdminReviewService(session).escalate_overdue_reviews(
        actor=actor,
        payload=payload,
    )
    return _to_escalation_response(result)


@router.get("/reviews", response_model=list[AdminReviewResponse])
async def list_reviews(
    actor: SuperuserActorDep,
    session: SessionDep,
    organization_id: UUID | None = None,
    status: AdminReviewStatus | None = None,
    priority: AdminReviewPriority | None = None,
    assigned_to_user_id: UUID | None = None,
    assigned_to_me: bool = False,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: int = LIMIT_QUERY,
) -> list[AdminReviewResponse]:
    reviews = AdminReviewService(session).list_reviews(
        actor=actor,
        organization_id=organization_id,
        status=status,
        priority=priority,
        assigned_to_user_id=assigned_to_user_id,
        assigned_to_me=assigned_to_me,
        search=search,
        limit=limit,
    )
    return [_to_review_response(review) for review in reviews]


@router.get("/organizations/{organization_id}/reviews", response_model=list[AdminReviewResponse])
async def list_organization_reviews(
    organization_id: UUID,
    actor: SuperuserActorDep,
    session: SessionDep,
    status: AdminReviewStatus | None = None,
    priority: AdminReviewPriority | None = None,
    assigned_to_user_id: UUID | None = None,
    assigned_to_me: bool = False,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    limit: int = LIMIT_QUERY,
) -> list[AdminReviewResponse]:
    reviews = AdminReviewService(session).list_reviews(
        actor=actor,
        organization_id=organization_id,
        status=status,
        priority=priority,
        assigned_to_user_id=assigned_to_user_id,
        assigned_to_me=assigned_to_me,
        search=search,
        limit=limit,
    )
    return [_to_review_response(review) for review in reviews]


@router.post(
    "/organizations/{organization_id}/reviews",
    response_model=AdminReviewDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    organization_id: UUID,
    payload: AdminReviewCreateRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewDetailResponse:
    review = AdminReviewService(session).create_review(
        actor=actor,
        organization_id=organization_id,
        payload=payload,
    )
    return _to_review_detail_response(review)


@router.get("/reviews/{review_id}", response_model=AdminReviewDetailResponse)
async def get_review(
    review_id: UUID,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewDetailResponse:
    review = AdminReviewService(session).get_review(actor=actor, review_id=review_id)
    return _to_review_detail_response(review)


@router.patch("/reviews/{review_id}", response_model=AdminReviewDetailResponse)
async def update_review(
    review_id: UUID,
    payload: AdminReviewUpdateRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewDetailResponse:
    review = AdminReviewService(session).update_review(
        actor=actor,
        review_id=review_id,
        payload=payload,
    )
    return _to_review_detail_response(review)


@router.post(
    "/reviews/{review_id}/comments",
    response_model=AdminReviewCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_comment(
    review_id: UUID,
    payload: AdminReviewCommentCreateRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminReviewCommentResponse:
    comment = AdminReviewService(session).create_comment(
        actor=actor,
        review_id=review_id,
        payload=payload,
    )
    return _to_review_comment_response(comment)


def _to_review_summary_response(summary: AdminReviewSummary) -> AdminReviewSummaryResponse:
    return AdminReviewSummaryResponse(
        total_reviews=summary.total_reviews,
        counts_by_status=summary.counts_by_status,
        counts_by_priority=summary.counts_by_priority,
        active_review_count=summary.active_review_count,
        overdue_review_count=summary.overdue_review_count,
        due_today_count=summary.due_today_count,
        unassigned_active_review_count=summary.unassigned_active_review_count,
    )


def _to_auto_open_preview_response(
    candidate: AdminReviewAutoOpenCandidate,
) -> AdminReviewAutoOpenPreviewItemResponse:
    return AdminReviewAutoOpenPreviewItemResponse(
        organization=AdminReviewOrganizationResponse(
            id=candidate.organization.id,
            name=candidate.organization.name,
            slug=candidate.organization.slug,
            status=candidate.organization.status,
        ),
        risk_score=candidate.risk_score,
        risk_level=candidate.risk_level,
        anomaly_count=candidate.anomaly_count,
        top_anomaly_codes=candidate.top_anomaly_codes,
        has_active_review=candidate.has_active_review,
        active_review_id=candidate.active_review_id,
        suggested_priority=candidate.suggested_priority,
        suggested_title=candidate.suggested_title,
    )


def _to_auto_open_response(result: AdminReviewAutoOpenResult) -> AdminReviewAutoOpenResponse:
    return AdminReviewAutoOpenResponse(
        created_count=result.created_count,
        skipped_count=result.skipped_count,
        results=[_to_auto_open_result_item_response(item) for item in result.results],
    )


def _to_auto_assign_preview_response(
    item: AdminReviewAutoAssignPreviewItem,
) -> AdminReviewAutoAssignPreviewItemResponse:
    return AdminReviewAutoAssignPreviewItemResponse(
        review_id=item.review_id,
        organization=AdminReviewOrganizationResponse(
            id=item.organization.id,
            name=item.organization.name,
            slug=item.organization.slug,
            status=item.organization.status,
        ),
        title=item.title,
        priority=item.priority,
        due_at=item.due_at,
        attention_reasons=item.attention_reasons,
        suggested_assignee=_to_review_user_response(item.suggested_assignee),
        current_assignee_load=item.current_assignee_load,
        projected_assignee_load=item.projected_assignee_load,
    )


def _to_auto_assign_response(
    result: AdminReviewAutoAssignResult,
) -> AdminReviewAutoAssignResponse:
    return AdminReviewAutoAssignResponse(
        assigned_count=result.assigned_count,
        skipped_count=result.skipped_count,
        results=[_to_auto_assign_result_item_response(item) for item in result.results],
    )


def _to_auto_assign_result_item_response(
    item: AdminReviewAutoAssignResultItem,
) -> AdminReviewAutoAssignResultItemResponse:
    return AdminReviewAutoAssignResultItemResponse(
        review_id=item.review_id,
        organization=AdminReviewOrganizationResponse(
            id=item.organization.id,
            name=item.organization.name,
            slug=item.organization.slug,
            status=item.organization.status,
        ),
        outcome=item.outcome,
        reason=item.reason,
        assigned_to=_to_review_user_response(item.assigned_to),
        added_comment=item.added_comment,
    )


def _to_auto_open_result_item_response(
    item: AdminReviewAutoOpenResultItem,
) -> AdminReviewAutoOpenResultItemResponse:
    return AdminReviewAutoOpenResultItemResponse(
        organization=AdminReviewOrganizationResponse(
            id=item.organization.id,
            name=item.organization.name,
            slug=item.organization.slug,
            status=item.organization.status,
        ),
        outcome=item.outcome,
        review_id=item.review_id,
        reason=item.reason,
        risk_score=item.risk_score,
        suggested_priority=item.suggested_priority,
    )


def _to_escalation_preview_response(
    item: AdminReviewEscalationPreviewItem,
) -> AdminReviewEscalationPreviewItemResponse:
    return AdminReviewEscalationPreviewItemResponse(
        review_id=item.review_id,
        organization=AdminReviewOrganizationResponse(
            id=item.organization.id,
            name=item.organization.name,
            slug=item.organization.slug,
            status=item.organization.status,
        ),
        title=item.title,
        priority=item.priority,
        due_at=item.due_at,
        assigned_to=_to_review_user_response(item.assigned_to),
        days_overdue=item.days_overdue,
        risk_score_snapshot=item.risk_score_snapshot,
        risk_level_snapshot=item.risk_level_snapshot,
        needs_priority_bump=item.needs_priority_bump,
        is_unassigned=item.is_unassigned,
    )


def _to_escalation_response(
    result: AdminReviewEscalateOverdueResult,
) -> AdminReviewEscalateOverdueResponse:
    return AdminReviewEscalateOverdueResponse(
        escalated_count=result.escalated_count,
        skipped_count=result.skipped_count,
        results=[_to_escalation_result_item_response(item) for item in result.results],
    )


def _to_escalation_result_item_response(
    item: AdminReviewEscalationResultItem,
) -> AdminReviewEscalationResultItemResponse:
    return AdminReviewEscalationResultItemResponse(
        review_id=item.review_id,
        organization=AdminReviewOrganizationResponse(
            id=item.organization.id,
            name=item.organization.name,
            slug=item.organization.slug,
            status=item.organization.status,
        ),
        outcome=item.outcome,
        reason=item.reason,
        previous_priority=item.previous_priority,
        current_priority=item.current_priority,
        assigned_to=_to_review_user_response(item.assigned_to),
        days_overdue=item.days_overdue,
        added_comment=item.added_comment,
    )


def _to_review_response(review: AdminReviewListItem) -> AdminReviewResponse:
    return AdminReviewResponse(
        id=review.id,
        organization=AdminReviewOrganizationResponse(
            id=review.organization.id,
            name=review.organization.name,
            slug=review.organization.slug,
            status=review.organization.status,
        ),
        title=review.title,
        summary=review.summary,
        status=review.status,
        priority=review.priority,
        due_at=review.due_at,
        resolved_at=review.resolved_at,
        risk_score_snapshot=review.risk_score_snapshot,
        risk_level_snapshot=review.risk_level_snapshot,
        anomaly_count_snapshot=review.anomaly_count_snapshot,
        top_anomaly_codes_snapshot=review.top_anomaly_codes_snapshot,
        created_by=_to_review_user_response(review.created_by),
        assigned_to=_to_review_user_response(review.assigned_to),
        comment_count=review.comment_count,
        last_comment_at=review.last_comment_at,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _to_review_workload_response(
    item: AdminReviewWorkloadItem,
) -> AdminReviewWorkloadResponse:
    return AdminReviewWorkloadResponse(
        assignee=_to_review_user_response(item.assignee),
        active_review_count=item.active_review_count,
        organization_count=item.organization_count,
        urgent_review_count=item.urgent_review_count,
        overdue_review_count=item.overdue_review_count,
        due_today_count=item.due_today_count,
        due_soon_count=item.due_soon_count,
        top_review_id=item.top_review_id,
        oldest_due_at=item.oldest_due_at,
        most_recent_update_at=item.most_recent_update_at,
    )


def _to_review_attention_response(
    item: AdminReviewAttentionItem,
) -> AdminReviewAttentionResponse:
    review = item.review
    return AdminReviewAttentionResponse(
        id=review.id,
        organization=AdminReviewOrganizationResponse(
            id=review.organization.id,
            name=review.organization.name,
            slug=review.organization.slug,
            status=review.organization.status,
        ),
        title=review.title,
        summary=review.summary,
        status=review.status,
        priority=review.priority,
        due_at=review.due_at,
        resolved_at=review.resolved_at,
        risk_score_snapshot=review.risk_score_snapshot,
        risk_level_snapshot=review.risk_level_snapshot,
        anomaly_count_snapshot=review.anomaly_count_snapshot,
        top_anomaly_codes_snapshot=review.top_anomaly_codes_snapshot,
        created_by=_to_review_user_response(review.created_by),
        assigned_to=_to_review_user_response(review.assigned_to),
        comment_count=review.comment_count,
        last_comment_at=review.last_comment_at,
        created_at=review.created_at,
        updated_at=review.updated_at,
        attention_reasons=item.attention_reasons,
        days_overdue=item.days_overdue,
        hours_until_due=item.hours_until_due,
    )


def _to_review_detail_response(review: AdminReviewDetail) -> AdminReviewDetailResponse:
    return AdminReviewDetailResponse(
        id=review.id,
        organization=AdminReviewOrganizationResponse(
            id=review.organization.id,
            name=review.organization.name,
            slug=review.organization.slug,
            status=review.organization.status,
        ),
        title=review.title,
        summary=review.summary,
        status=review.status,
        priority=review.priority,
        due_at=review.due_at,
        resolved_at=review.resolved_at,
        risk_score_snapshot=review.risk_score_snapshot,
        risk_level_snapshot=review.risk_level_snapshot,
        anomaly_count_snapshot=review.anomaly_count_snapshot,
        top_anomaly_codes_snapshot=review.top_anomaly_codes_snapshot,
        created_by=_to_review_user_response(review.created_by),
        assigned_to=_to_review_user_response(review.assigned_to),
        comment_count=review.comment_count,
        last_comment_at=review.last_comment_at,
        created_at=review.created_at,
        updated_at=review.updated_at,
        comments=[_to_review_comment_response(comment) for comment in review.comments],
    )


def _to_review_comment_response(comment: AdminReviewCommentItem) -> AdminReviewCommentResponse:
    return AdminReviewCommentResponse(
        id=comment.id,
        author=_to_review_user_response(comment.author),
        body=comment.body,
        created_at=comment.created_at,
    )


def _to_review_user_response(user: AdminReviewUserRef | None) -> AdminReviewUserResponse | None:
    if user is None:
        return None
    return AdminReviewUserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
    )
