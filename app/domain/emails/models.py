"""Outbound email persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, UUIDPrimaryKeyMixin


class OutboundEmailStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class OutboundEmail(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "outbound_emails"

    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    template_key: Mapped[str] = mapped_column(String(120), index=True)
    recipient_email: Mapped[str] = mapped_column(String(320), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    status: Mapped[OutboundEmailStatus] = mapped_column(
        Enum(OutboundEmailStatus, name="outbound_email_status", native_enum=False),
        default=OutboundEmailStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    delivery_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), index=True)
