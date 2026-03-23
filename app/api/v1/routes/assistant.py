"""Case assistant routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.assistant import (
    AssistantConversationCreateRequest,
    AssistantConversationResponse,
    AssistantExchangeResponse,
    AssistantMessageCreateRequest,
    AssistantMessageResponse,
)
from app.application.services.assistant import AssistantService
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/cases/{case_id}/assistant")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


@router.get("/conversations", response_model=list[AssistantConversationResponse])
async def list_assistant_conversations(
    case_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[AssistantConversationResponse]:
    conversations = AssistantService(session).list_conversations(actor=actor, case_id=case_id)
    return [
        AssistantConversationResponse.model_validate(conversation, from_attributes=True)
        for conversation in conversations
    ]


@router.post(
    "/conversations",
    response_model=AssistantConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assistant_conversation(
    case_id: UUID,
    payload: AssistantConversationCreateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> AssistantConversationResponse:
    conversation = AssistantService(session).create_conversation(
        actor=actor,
        case_id=case_id,
        payload=payload,
    )
    return AssistantConversationResponse.model_validate(conversation, from_attributes=True)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[AssistantMessageResponse],
)
async def list_assistant_messages(
    case_id: UUID,
    conversation_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[AssistantMessageResponse]:
    messages = AssistantService(session).list_messages(
        actor=actor,
        case_id=case_id,
        conversation_id=conversation_id,
    )
    return [
        AssistantMessageResponse.model_validate(message, from_attributes=True)
        for message in messages
    ]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AssistantExchangeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ask_case_assistant(
    case_id: UUID,
    conversation_id: UUID,
    payload: AssistantMessageCreateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> AssistantExchangeResponse:
    exchange = AssistantService(session).ask(
        actor=actor,
        case_id=case_id,
        conversation_id=conversation_id,
        payload=payload,
    )
    return AssistantExchangeResponse(
        conversation=AssistantConversationResponse.model_validate(
            exchange.conversation,
            from_attributes=True,
        ),
        user_message=AssistantMessageResponse.model_validate(
            exchange.user_message,
            from_attributes=True,
        ),
        assistant_message=AssistantMessageResponse.model_validate(
            exchange.assistant_message,
            from_attributes=True,
        ),
    )
