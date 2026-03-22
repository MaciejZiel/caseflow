"""API key management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.api_keys import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
)
from app.application.services.api_keys import ApiKeyService
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/api-keys")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> ApiKeyCreatedResponse:
    result = ApiKeyService(session).create_api_key(actor=actor, payload=payload)
    return _build_created_response(result.api_key, plaintext_key=result.plaintext_key)


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(actor: CurrentActorDep, session: SessionDep) -> list[ApiKeyResponse]:
    api_keys = ApiKeyService(session).list_api_keys(actor=actor)
    return [_build_api_key_response(api_key) for api_key in api_keys]


@router.post("/{api_key_id}/revoke", response_model=ApiKeyResponse)
async def revoke_api_key(
    api_key_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> ApiKeyResponse:
    api_key = ApiKeyService(session).revoke_api_key(actor=actor, api_key_id=api_key_id)
    return _build_api_key_response(api_key)


def _build_created_response(api_key, *, plaintext_key: str) -> ApiKeyCreatedResponse:
    return ApiKeyCreatedResponse(
        **_build_api_key_response(api_key).model_dump(),
        plaintext_key=plaintext_key,
    )


def _build_api_key_response(api_key) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        name=api_key.name,
        description=api_key.description,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes_json,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        last_used_ip=api_key.last_used_ip,
        revoked_at=api_key.revoked_at,
        revoke_reason=api_key.revoke_reason,
        created_at=api_key.created_at,
    )
