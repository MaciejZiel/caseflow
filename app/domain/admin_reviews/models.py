"""Platform admin review workflow persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.domain.users.models import User


class AdminReviewStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AdminReviewPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AdminOrganizationReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_organization_reviews"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AdminReviewStatus] = mapped_column(
        Enum(AdminReviewStatus, name="admin_review_status", native_enum=False),
        default=AdminReviewStatus.OPEN,
        index=True,
    )
    priority: Mapped[AdminReviewPriority] = mapped_column(
        Enum(AdminReviewPriority, name="admin_review_priority", native_enum=False),
        default=AdminReviewPriority.NORMAL,
        index=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_score_snapshot: Mapped[int] = mapped_column(Integer, default=0)
    risk_level_snapshot: Mapped[str] = mapped_column(String(20), default="healthy")
    anomaly_count_snapshot: Mapped[int] = mapped_column(Integer, default=0)
    top_anomaly_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)

    comments: Mapped[list[AdminOrganizationReviewComment]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="AdminOrganizationReviewComment.created_at.asc()",
    )
    created_by_user: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    assigned_to_user: Mapped[User | None] = relationship(foreign_keys=[assigned_to_user_id])


class AdminOrganizationReviewComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_organization_review_comments"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    review_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_organization_reviews.id", ondelete="CASCADE"),
        index=True,
    )
    author_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)

    review: Mapped[AdminOrganizationReview] = relationship(back_populates="comments")
    author_user: Mapped[User] = relationship()
