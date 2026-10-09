"""Assistant conversation persistence models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssistantPromptMode(StrEnum):
    GENERAL = "general"
    CASE_SUMMARY = "case_summary"
    REVIEW_ASSISTANT = "review_assistant"
    NEXT_ACTIONS = "next_actions"


class AssistantMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AssistantConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assistant_conversations"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    prompt_mode: Mapped[AssistantPromptMode] = mapped_column(
        Enum(AssistantPromptMode, name="assistant_prompt_mode", native_enum=False),
        default=AssistantPromptMode.GENERAL,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssistantMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "assistant_messages"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
        index=True,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[AssistantMessageRole] = mapped_column(
        Enum(AssistantMessageRole, name="assistant_message_role", native_enum=False),
    )
    prompt_mode: Mapped[AssistantPromptMode] = mapped_column(
        Enum(AssistantPromptMode, name="assistant_prompt_mode", native_enum=False),
    )
    content: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), index=True)
