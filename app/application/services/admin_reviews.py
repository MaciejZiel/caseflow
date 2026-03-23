"""Platform admin review workflow services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case as sql_case
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.admin_reviews import (
    AdminReviewAutoOpenRequest,
    AdminReviewCommentCreateRequest,
    AdminReviewCreateRequest,
    AdminReviewUpdateRequest,
)
from app.application.actors import ActorContext
from app.application.services.admin import AdminRiskReportItem, AdminService
from app.application.services.events import EventPublisher
from app.core.errors import DomainValidationError, NotFoundError, PermissionDeniedError
from app.domain.admin_reviews.models import (
    AdminOrganizationReview,
    AdminOrganizationReviewComment,
    AdminReviewPriority,
    AdminReviewStatus,
)
from app.domain.organizations.models import Organization, OrganizationStatus
from app.domain.users.models import User

ACTIVE_REVIEW_STATUSES = frozenset({AdminReviewStatus.OPEN, AdminReviewStatus.IN_PROGRESS})


@dataclass(slots=True)
class AdminReviewUserRef:
    id: UUID
    email: str
    first_name: str
    last_name: str


@dataclass(slots=True)
class AdminReviewOrganizationRef:
    id: UUID
    name: str
    slug: str
    status: OrganizationStatus


@dataclass(slots=True)
class AdminReviewCommentItem:
    id: UUID
    author: AdminReviewUserRef
    body: str
    created_at: datetime


@dataclass(slots=True)
class AdminReviewListItem:
    id: UUID
    organization: AdminReviewOrganizationRef
    title: str
    summary: str | None
    status: AdminReviewStatus
    priority: AdminReviewPriority
    due_at: datetime | None
    resolved_at: datetime | None
    risk_score_snapshot: int
    risk_level_snapshot: str
    anomaly_count_snapshot: int
    top_anomaly_codes_snapshot: list[str]
    created_by: AdminReviewUserRef
    assigned_to: AdminReviewUserRef | None
    comment_count: int
    last_comment_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AdminReviewDetail:
    id: UUID
    organization: AdminReviewOrganizationRef
    title: str
    summary: str | None
    status: AdminReviewStatus
    priority: AdminReviewPriority
    due_at: datetime | None
    resolved_at: datetime | None
    risk_score_snapshot: int
    risk_level_snapshot: str
    anomaly_count_snapshot: int
    top_anomaly_codes_snapshot: list[str]
    created_by: AdminReviewUserRef
    assigned_to: AdminReviewUserRef | None
    comment_count: int
    last_comment_at: datetime | None
    created_at: datetime
    updated_at: datetime
    comments: list[AdminReviewCommentItem]


@dataclass(slots=True)
class AdminReviewSummary:
    total_reviews: int
    counts_by_status: dict[str, int]
    counts_by_priority: dict[str, int]
    active_review_count: int
    overdue_review_count: int
    due_today_count: int
    unassigned_active_review_count: int


@dataclass(slots=True)
class AdminReviewAutoOpenCandidate:
    organization: AdminReviewOrganizationRef
    risk_score: int
    risk_level: str
    anomaly_count: int
    top_anomaly_codes: list[str]
    has_active_review: bool
    active_review_id: UUID | None
    suggested_priority: AdminReviewPriority
    suggested_title: str


@dataclass(slots=True)
class AdminReviewAutoOpenResultItem:
    organization: AdminReviewOrganizationRef
    outcome: str
    review_id: UUID | None
    reason: str | None
    risk_score: int
    suggested_priority: AdminReviewPriority


@dataclass(slots=True)
class AdminReviewAutoOpenResult:
    created_count: int
    skipped_count: int
    results: list[AdminReviewAutoOpenResultItem]


class AdminReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.publisher = EventPublisher(session)

    def get_review_summary(
        self,
        *,
        actor: ActorContext,
    ) -> AdminReviewSummary:
        self._ensure_superuser(actor)
        now = datetime.now(UTC)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_tomorrow = start_of_today + timedelta(days=1)
        active_statuses = tuple(ACTIVE_REVIEW_STATUSES)

        counts_by_status = {status.value: 0 for status in AdminReviewStatus}
        counts_by_priority = {priority.value: 0 for priority in AdminReviewPriority}

        for status_value, count in self.session.execute(
            select(AdminOrganizationReview.status, func.count(AdminOrganizationReview.id)).group_by(
                AdminOrganizationReview.status
            )
        ):
            counts_by_status[status_value.value] = count

        for priority_value, count in self.session.execute(
            select(
                AdminOrganizationReview.priority,
                func.count(AdminOrganizationReview.id),
            ).group_by(AdminOrganizationReview.priority)
        ):
            counts_by_priority[priority_value.value] = count

        return AdminReviewSummary(
            total_reviews=self._count_rows(
                select(func.count(AdminOrganizationReview.id)).select_from(AdminOrganizationReview)
            ),
            counts_by_status=counts_by_status,
            counts_by_priority=counts_by_priority,
            active_review_count=self._count_rows(
                select(func.count(AdminOrganizationReview.id))
                .select_from(AdminOrganizationReview)
                .where(AdminOrganizationReview.status.in_(active_statuses))
            ),
            overdue_review_count=self._count_rows(
                select(func.count(AdminOrganizationReview.id))
                .select_from(AdminOrganizationReview)
                .where(
                    AdminOrganizationReview.status.in_(active_statuses),
                    AdminOrganizationReview.due_at.is_not(None),
                    AdminOrganizationReview.due_at < now,
                )
            ),
            due_today_count=self._count_rows(
                select(func.count(AdminOrganizationReview.id))
                .select_from(AdminOrganizationReview)
                .where(
                    AdminOrganizationReview.status.in_(active_statuses),
                    AdminOrganizationReview.due_at.is_not(None),
                    AdminOrganizationReview.due_at >= start_of_today,
                    AdminOrganizationReview.due_at < start_of_tomorrow,
                )
            ),
            unassigned_active_review_count=self._count_rows(
                select(func.count(AdminOrganizationReview.id))
                .select_from(AdminOrganizationReview)
                .where(
                    AdminOrganizationReview.status.in_(active_statuses),
                    AdminOrganizationReview.assigned_to_user_id.is_(None),
                )
            ),
        )

    def preview_auto_open_candidates(
        self,
        *,
        actor: ActorContext,
        min_risk_score: int,
        limit: int,
    ) -> list[AdminReviewAutoOpenCandidate]:
        self._ensure_superuser(actor)
        risk_items = AdminService(self.session).list_risk_report(
            actor=actor,
            status=None,
            search=None,
            min_risk_score=min_risk_score,
            limit=limit,
        )
        active_review_ids = self._load_active_review_ids(
            {item.organization_id for item in risk_items}
        )
        return [
            self._build_auto_open_candidate(
                risk_item=item,
                active_review_id=active_review_ids.get(item.organization_id),
            )
            for item in risk_items
        ]

    def auto_open_reviews(
        self,
        *,
        actor: ActorContext,
        payload: AdminReviewAutoOpenRequest,
    ) -> AdminReviewAutoOpenResult:
        self._ensure_superuser(actor)
        candidates = self.preview_auto_open_candidates(
            actor=actor,
            min_risk_score=payload.min_risk_score,
            limit=payload.limit,
        )
        due_at = (
            datetime.now(UTC) + timedelta(days=payload.due_in_days)
            if payload.due_in_days is not None
            else None
        )

        results: list[AdminReviewAutoOpenResultItem] = []
        created_count = 0
        for candidate in candidates:
            if candidate.has_active_review:
                results.append(
                    AdminReviewAutoOpenResultItem(
                        organization=candidate.organization,
                        outcome="skipped",
                        review_id=candidate.active_review_id,
                        reason="active_review_exists",
                        risk_score=candidate.risk_score,
                        suggested_priority=candidate.suggested_priority,
                    )
                )
                continue

            review = self.create_review(
                actor=actor,
                organization_id=candidate.organization.id,
                payload=AdminReviewCreateRequest(
                    title=candidate.suggested_title,
                    summary=self._build_auto_open_summary(candidate),
                    assigned_to_user_id=payload.assigned_to_user_id,
                    due_at=due_at,
                ),
            )
            created_count += 1
            results.append(
                AdminReviewAutoOpenResultItem(
                    organization=candidate.organization,
                    outcome="created",
                    review_id=review.id,
                    reason=None,
                    risk_score=candidate.risk_score,
                    suggested_priority=candidate.suggested_priority,
                )
            )

        return AdminReviewAutoOpenResult(
            created_count=created_count,
            skipped_count=len(results) - created_count,
            results=results,
        )

    def list_reviews(
        self,
        *,
        actor: ActorContext,
        organization_id: UUID | None,
        status: AdminReviewStatus | None,
        priority: AdminReviewPriority | None,
        assigned_to_user_id: UUID | None,
        assigned_to_me: bool,
        search: str | None,
        limit: int,
    ) -> list[AdminReviewListItem]:
        self._ensure_superuser(actor)
        normalized_search = " ".join(search.split()).strip().lower() if search else None
        effective_assignee = actor.user.id if assigned_to_me else assigned_to_user_id

        query = select(AdminOrganizationReview)
        if normalized_search is not None:
            query = query.join(
                Organization,
                Organization.id == AdminOrganizationReview.organization_id,
            ).where(
                or_(
                    func.lower(AdminOrganizationReview.title).contains(normalized_search),
                    func.lower(func.coalesce(AdminOrganizationReview.summary, "")).contains(
                        normalized_search
                    ),
                    func.lower(Organization.name).contains(normalized_search),
                    func.lower(Organization.slug).contains(normalized_search),
                )
            )
        if organization_id is not None:
            query = query.where(AdminOrganizationReview.organization_id == organization_id)
        if status is not None:
            query = query.where(AdminOrganizationReview.status == status)
        if priority is not None:
            query = query.where(AdminOrganizationReview.priority == priority)
        if effective_assignee is not None:
            query = query.where(AdminOrganizationReview.assigned_to_user_id == effective_assignee)

        active_rank = sql_case(
            (AdminOrganizationReview.status.in_(tuple(ACTIVE_REVIEW_STATUSES)), 0),
            else_=1,
        )
        due_null_rank = sql_case((AdminOrganizationReview.due_at.is_(None), 1), else_=0)
        priority_rank = sql_case(
            (AdminOrganizationReview.priority == AdminReviewPriority.URGENT, 0),
            (AdminOrganizationReview.priority == AdminReviewPriority.HIGH, 1),
            (AdminOrganizationReview.priority == AdminReviewPriority.NORMAL, 2),
            else_=3,
        )
        reviews = list(
            self.session.scalars(
                query.order_by(
                    active_rank.asc(),
                    due_null_rank.asc(),
                    AdminOrganizationReview.due_at.asc(),
                    priority_rank.asc(),
                    AdminOrganizationReview.updated_at.desc(),
                ).limit(limit)
            )
        )
        return self._build_review_list_items(reviews)

    def get_review(
        self,
        *,
        actor: ActorContext,
        review_id: UUID,
    ) -> AdminReviewDetail:
        self._ensure_superuser(actor)
        review = self._get_review(review_id)
        return self._build_review_detail(review)

    def create_review(
        self,
        *,
        actor: ActorContext,
        organization_id: UUID,
        payload: AdminReviewCreateRequest,
    ) -> AdminReviewDetail:
        self._ensure_superuser(actor)
        organization = self._get_organization(organization_id)
        self._ensure_no_active_review(organization_id=organization.id, exclude_review_id=None)

        assignee = self._resolve_assignee(payload.assigned_to_user_id)
        risk_snapshot = AdminService(self.session).get_organization_risk_report(
            actor=actor,
            organization_id=organization.id,
        )
        review = AdminOrganizationReview(
            organization_id=organization.id,
            created_by_user_id=actor.user.id,
            assigned_to_user_id=assignee.id if assignee is not None else None,
            title=payload.title,
            summary=payload.summary,
            priority=payload.priority or self._priority_from_risk_score(risk_snapshot.risk_score),
            due_at=payload.due_at,
            risk_score_snapshot=risk_snapshot.risk_score,
            risk_level_snapshot=risk_snapshot.risk_level,
            anomaly_count_snapshot=risk_snapshot.anomaly_count,
            top_anomaly_codes_json=risk_snapshot.top_anomaly_codes,
        )
        self.session.add(review)
        self.session.flush()
        self.publisher.record_event(
            organization_id=organization.id,
            actor_user_id=actor.user.id,
            event_type="admin_review.created",
            entity_type="admin_review",
            entity_id=review.id,
            new_values=self._review_snapshot(review),
            metadata={
                "organization_slug": organization.slug,
                "assigned_to_user_id": assignee.id if assignee is not None else None,
            },
            deliver_webhooks=False,
        )
        self.session.commit()
        return self.get_review(actor=actor, review_id=review.id)

    def update_review(
        self,
        *,
        actor: ActorContext,
        review_id: UUID,
        payload: AdminReviewUpdateRequest,
    ) -> AdminReviewDetail:
        self._ensure_superuser(actor)
        review = self._get_review(review_id)
        old_values = self._review_snapshot(review)

        if "assigned_to_user_id" in payload.model_fields_set:
            assignee = self._resolve_assignee(payload.assigned_to_user_id)
            review.assigned_to_user_id = assignee.id if assignee is not None else None
        if "title" in payload.model_fields_set:
            review.title = payload.title
        if "summary" in payload.model_fields_set:
            review.summary = payload.summary
        if "priority" in payload.model_fields_set:
            review.priority = payload.priority
        if "due_at" in payload.model_fields_set:
            review.due_at = payload.due_at
        if "status" in payload.model_fields_set:
            if payload.status in ACTIVE_REVIEW_STATUSES:
                self._ensure_no_active_review(
                    organization_id=review.organization_id,
                    exclude_review_id=review.id,
                )
                review.resolved_at = None
            elif review.status not in {AdminReviewStatus.RESOLVED, AdminReviewStatus.DISMISSED}:
                review.resolved_at = datetime.now(UTC)
            review.status = payload.status

        self.session.flush()
        new_values = self._review_snapshot(review)
        if old_values != new_values:
            self.publisher.record_event(
                organization_id=review.organization_id,
                actor_user_id=actor.user.id,
                event_type="admin_review.updated",
                entity_type="admin_review",
                entity_id=review.id,
                old_values=old_values,
                new_values=new_values,
                metadata={"updated_fields": sorted(payload.model_fields_set)},
                deliver_webhooks=False,
            )
        self.session.commit()
        return self.get_review(actor=actor, review_id=review.id)

    def create_comment(
        self,
        *,
        actor: ActorContext,
        review_id: UUID,
        payload: AdminReviewCommentCreateRequest,
    ) -> AdminReviewCommentItem:
        self._ensure_superuser(actor)
        review = self._get_review(review_id)
        comment = AdminOrganizationReviewComment(
            organization_id=review.organization_id,
            review_id=review.id,
            author_user_id=actor.user.id,
            body=payload.body,
        )
        self.session.add(comment)
        self.session.flush()
        self.publisher.record_event(
            organization_id=review.organization_id,
            actor_user_id=actor.user.id,
            event_type="admin_review.comment_added",
            entity_type="admin_review",
            entity_id=review.id,
            new_values={"comment_id": comment.id},
            metadata={"body_excerpt": payload.body[:120]},
            deliver_webhooks=False,
        )
        self.session.commit()
        return self._build_comment_item(
            comment=comment,
            authors={
                actor.user.id: AdminReviewUserRef(
                    id=actor.user.id,
                    email=actor.user.email,
                    first_name=actor.user.first_name,
                    last_name=actor.user.last_name,
                )
            },
        )

    def _build_review_list_items(
        self,
        reviews: list[AdminOrganizationReview],
    ) -> list[AdminReviewListItem]:
        if not reviews:
            return []

        organization_ids = {review.organization_id for review in reviews}
        user_ids = {review.created_by_user_id for review in reviews}
        user_ids.update(
            review.assigned_to_user_id
            for review in reviews
            if review.assigned_to_user_id is not None
        )
        review_ids = [review.id for review in reviews]

        organizations = self._load_organizations(organization_ids)
        users = self._load_users(user_ids)
        comment_stats = {
            review_id: (comment_count, last_comment_at)
            for review_id, comment_count, last_comment_at in self.session.execute(
                select(
                    AdminOrganizationReviewComment.review_id,
                    func.count(AdminOrganizationReviewComment.id),
                    func.max(AdminOrganizationReviewComment.created_at),
                )
                .where(AdminOrganizationReviewComment.review_id.in_(review_ids))
                .group_by(AdminOrganizationReviewComment.review_id)
            )
        }

        items: list[AdminReviewListItem] = []
        for review in reviews:
            comment_count, last_comment_at = comment_stats.get(review.id, (0, None))
            items.append(
                AdminReviewListItem(
                    id=review.id,
                    organization=organizations[review.organization_id],
                    title=review.title,
                    summary=review.summary,
                    status=review.status,
                    priority=review.priority,
                    due_at=review.due_at,
                    resolved_at=review.resolved_at,
                    risk_score_snapshot=review.risk_score_snapshot,
                    risk_level_snapshot=review.risk_level_snapshot,
                    anomaly_count_snapshot=review.anomaly_count_snapshot,
                    top_anomaly_codes_snapshot=list(review.top_anomaly_codes_json or []),
                    created_by=users[review.created_by_user_id],
                    assigned_to=(
                        users[review.assigned_to_user_id]
                        if review.assigned_to_user_id is not None
                        else None
                    ),
                    comment_count=comment_count,
                    last_comment_at=last_comment_at,
                    created_at=review.created_at,
                    updated_at=review.updated_at,
                )
            )
        return items

    def _build_review_detail(
        self,
        review: AdminOrganizationReview,
    ) -> AdminReviewDetail:
        base_item = self._build_review_list_items([review])[0]
        comments = list(
            self.session.scalars(
                select(AdminOrganizationReviewComment)
                .where(AdminOrganizationReviewComment.review_id == review.id)
                .order_by(AdminOrganizationReviewComment.created_at.asc())
            )
        )
        comment_authors = self._load_users({comment.author_user_id for comment in comments})
        return AdminReviewDetail(
            id=base_item.id,
            organization=base_item.organization,
            title=base_item.title,
            summary=base_item.summary,
            status=base_item.status,
            priority=base_item.priority,
            due_at=base_item.due_at,
            resolved_at=base_item.resolved_at,
            risk_score_snapshot=base_item.risk_score_snapshot,
            risk_level_snapshot=base_item.risk_level_snapshot,
            anomaly_count_snapshot=base_item.anomaly_count_snapshot,
            top_anomaly_codes_snapshot=base_item.top_anomaly_codes_snapshot,
            created_by=base_item.created_by,
            assigned_to=base_item.assigned_to,
            comment_count=base_item.comment_count,
            last_comment_at=base_item.last_comment_at,
            created_at=base_item.created_at,
            updated_at=base_item.updated_at,
            comments=[
                self._build_comment_item(comment=comment, authors=comment_authors)
                for comment in comments
            ],
        )

    def _load_active_review_ids(
        self,
        organization_ids: set[UUID],
    ) -> dict[UUID, UUID]:
        if not organization_ids:
            return {}
        active_review_ids: dict[UUID, UUID] = {}
        rows = self.session.execute(
            select(
                AdminOrganizationReview.organization_id,
                AdminOrganizationReview.id,
            )
            .where(
                AdminOrganizationReview.organization_id.in_(organization_ids),
                AdminOrganizationReview.status.in_(tuple(ACTIVE_REVIEW_STATUSES)),
            )
            .order_by(AdminOrganizationReview.updated_at.desc())
        )
        for organization_id, review_id in rows:
            active_review_ids.setdefault(organization_id, review_id)
        return active_review_ids

    def _build_auto_open_candidate(
        self,
        *,
        risk_item: AdminRiskReportItem,
        active_review_id: UUID | None,
    ) -> AdminReviewAutoOpenCandidate:
        organization = AdminReviewOrganizationRef(
            id=risk_item.organization_id,
            name=risk_item.organization_name,
            slug=risk_item.organization_slug,
            status=risk_item.status,
        )
        return AdminReviewAutoOpenCandidate(
            organization=organization,
            risk_score=risk_item.risk_score,
            risk_level=risk_item.risk_level,
            anomaly_count=risk_item.anomaly_count,
            top_anomaly_codes=list(risk_item.top_anomaly_codes),
            has_active_review=active_review_id is not None,
            active_review_id=active_review_id,
            suggested_priority=self._priority_from_risk_score(risk_item.risk_score),
            suggested_title=(
                f"Platform review: {risk_item.organization_name} "
                f"({risk_item.risk_level} risk)"
            ),
        )

    @staticmethod
    def _build_auto_open_summary(candidate: AdminReviewAutoOpenCandidate) -> str:
        top_anomalies = ", ".join(candidate.top_anomaly_codes) or "no anomaly codes"
        return (
            "Opened automatically from the platform risk report. "
            f"Risk score: {candidate.risk_score}. "
            f"Risk level: {candidate.risk_level}. "
            f"Anomalies detected: {candidate.anomaly_count}. "
            f"Top anomaly codes: {top_anomalies}."
        )

    def _build_comment_item(
        self,
        *,
        comment: AdminOrganizationReviewComment,
        authors: dict[UUID, AdminReviewUserRef],
    ) -> AdminReviewCommentItem:
        return AdminReviewCommentItem(
            id=comment.id,
            author=authors[comment.author_user_id],
            body=comment.body,
            created_at=comment.created_at,
        )

    def _load_organizations(
        self,
        organization_ids: set[UUID],
    ) -> dict[UUID, AdminReviewOrganizationRef]:
        if not organization_ids:
            return {}
        return {
            organization_id: AdminReviewOrganizationRef(
                id=organization_id,
                name=name,
                slug=slug,
                status=status,
            )
            for organization_id, name, slug, status in self.session.execute(
                select(
                    Organization.id,
                    Organization.name,
                    Organization.slug,
                    Organization.status,
                ).where(Organization.id.in_(organization_ids))
            )
        }

    def _load_users(
        self,
        user_ids: set[UUID],
    ) -> dict[UUID, AdminReviewUserRef]:
        if not user_ids:
            return {}
        return {
            user_id: AdminReviewUserRef(
                id=user_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
            for user_id, email, first_name, last_name in self.session.execute(
                select(
                    User.id,
                    User.email,
                    User.first_name,
                    User.last_name,
                ).where(User.id.in_(user_ids))
            )
        }

    def _resolve_assignee(self, user_id: UUID | None) -> User | None:
        if user_id is None:
            return None
        user = self.session.get(User, user_id)
        if user is None or not user.is_active or not user.is_superuser:
            raise DomainValidationError(
                "admin_review_assignee_invalid",
                "Platform reviews can only be assigned to active superusers.",
            )
        return user

    def _ensure_no_active_review(
        self,
        *,
        organization_id: UUID,
        exclude_review_id: UUID | None,
    ) -> None:
        query = (
            select(func.count(AdminOrganizationReview.id))
            .select_from(AdminOrganizationReview)
            .where(
                AdminOrganizationReview.organization_id == organization_id,
                AdminOrganizationReview.status.in_(tuple(ACTIVE_REVIEW_STATUSES)),
            )
        )
        if exclude_review_id is not None:
            query = query.where(AdminOrganizationReview.id != exclude_review_id)
        if self._count_rows(query) > 0:
            raise DomainValidationError(
                "organization_review_already_open",
                "Only one active platform review can exist for an organization at a time.",
            )

    def _get_review(self, review_id: UUID) -> AdminOrganizationReview:
        review = self.session.get(AdminOrganizationReview, review_id)
        if review is None:
            raise NotFoundError("admin_review", "Platform review does not exist.")
        return review

    def _get_organization(self, organization_id: UUID) -> Organization:
        organization = self.session.get(Organization, organization_id)
        if organization is None:
            raise NotFoundError("organization", "Organization does not exist.")
        return organization

    @staticmethod
    def _ensure_superuser(actor: ActorContext) -> None:
        if not actor.user.is_superuser:
            raise PermissionDeniedError("Only platform admins can access admin review endpoints.")

    @staticmethod
    def _review_snapshot(review: AdminOrganizationReview) -> dict[str, object]:
        return {
            "title": review.title,
            "summary": review.summary,
            "status": review.status,
            "priority": review.priority,
            "due_at": review.due_at,
            "resolved_at": review.resolved_at,
            "assigned_to_user_id": review.assigned_to_user_id,
            "risk_score_snapshot": review.risk_score_snapshot,
            "risk_level_snapshot": review.risk_level_snapshot,
            "anomaly_count_snapshot": review.anomaly_count_snapshot,
            "top_anomaly_codes_snapshot": list(review.top_anomaly_codes_json or []),
        }

    @staticmethod
    def _priority_from_risk_score(risk_score: int) -> AdminReviewPriority:
        if risk_score >= 100:
            return AdminReviewPriority.URGENT
        if risk_score >= 50:
            return AdminReviewPriority.HIGH
        if risk_score >= 20:
            return AdminReviewPriority.NORMAL
        return AdminReviewPriority.LOW

    def _count_rows(self, statement) -> int:
        return int(self.session.scalar(statement) or 0)
