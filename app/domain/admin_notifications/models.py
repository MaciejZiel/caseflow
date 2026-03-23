"""Platform admin notification persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AdminNotificationType(StrEnum):
    REVIEW_AUTO_OPENED = "review_auto_opened"
    REVIEW_OVERDUE_ESCALATED = "review_overdue_escalated"


class AdminNotification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "admin_notifications"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    review_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("admin_organization_reviews.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    notification_type: Mapped[AdminNotificationType] = mapped_column(
        Enum(
            AdminNotificationType,
            name="admin_notification_type",
            native_enum=False,
        ),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), index=True)


class AdminNotificationPreference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_notification_preferences"
    __table_args__ = (UniqueConstraint("user_id"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_review_auto_opened: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_review_overdue_escalated: Mapped[bool] = mapped_column(Boolean, default=True)
