"""Schemas for assistant conversations and grounded responses."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.assistant.models import AssistantMessageRole, AssistantPromptMode


class AssistantConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    prompt_mode: AssistantPromptMode = AssistantPromptMode.GENERAL


class AssistantConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    title: str
    prompt_mode: AssistantPromptMode
    created_by_user_id: UUID
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssistantCitationResponse(BaseModel):
    document_id: UUID
    document_title: str
    document_type: str
    document_status: str
    document_version_id: UUID | None
    original_filename: str | None
    excerpt: str
    score: int


class AssistantMessageCreateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=5_000)
    prompt_mode: AssistantPromptMode | None = None


class AssistantMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    actor_user_id: UUID | None
    role: AssistantMessageRole
    prompt_mode: AssistantPromptMode
    content: str
    citations_json: list[AssistantCitationResponse]
    metadata_json: dict[str, object]
    created_at: datetime


class AssistantExchangeResponse(BaseModel):
    conversation: AssistantConversationResponse
    user_message: AssistantMessageResponse
    assistant_message: AssistantMessageResponse
