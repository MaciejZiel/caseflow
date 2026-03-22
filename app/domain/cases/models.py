"""Case persistence models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CaseStatus(StrEnum):
    NEW = "new"
    IN_REVIEW = "in_review"
    WAITING_FOR_DOCUMENTS = "waiting_for_documents"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class CasePriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Case(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("organization_id", "external_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, name="case_status", native_enum=False),
        default=CaseStatus.NEW,
        index=True,
    )
    priority: Mapped[CasePriority] = mapped_column(
        Enum(CasePriority, name="case_priority", native_enum=False),
        default=CasePriority.NORMAL,
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "case_comments"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
    )
    author_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
