"""Platform admin review workflow routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import SuperuserActor, get_current_superuser_actor
from app.api.v1.schemas.admin_reviews import (
    AdminReviewAutoOpenPreviewItemResponse,
    AdminReviewAutoOpenRequest,
    AdminReviewAutoOpenResponse,
    AdminReviewAutoOpenResultItemResponse,
    AdminReviewCommentCreateRequest,
    AdminReviewCommentResponse,
    AdminReviewCreateRequest,
    AdminReviewDetailResponse,
    AdminReviewOrganizationResponse,
    AdminReviewResponse,
    AdminReviewSummaryResponse,
    AdminReviewUpdateRequest,
    AdminReviewUserResponse,
)
from app.application.services.admin_reviews import (
    AdminReviewAutoOpenCandidate,
    AdminReviewAutoOpenResult,
    AdminReviewAutoOpenResultItem,
    AdminReviewCommentItem,
    AdminReviewDetail,
    AdminReviewListItem,
    AdminReviewService,
    AdminReviewSummary,
    AdminReviewUserRef,
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
