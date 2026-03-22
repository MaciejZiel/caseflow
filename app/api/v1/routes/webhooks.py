"""Webhook management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import CurrentActor, get_current_actor
from app.api.v1.schemas.webhooks import (
    WebhookDeliveryResponse,
    WebhookEndpointCreateRequest,
    WebhookEndpointResponse,
    WebhookEndpointUpdateRequest,
)
from app.application.services.webhooks import WebhookService
from app.domain.webhooks.models import WebhookDeliveryStatus
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/webhooks")
SessionDep = Annotated[Session, Depends(get_db_session)]
CurrentActorDep = Annotated[CurrentActor, Depends(get_current_actor)]
LIMIT_QUERY = Query(default=20, ge=1, le=100)
OFFSET_QUERY = Query(default=0, ge=0)
STATUS_QUERY = Query(default=None)
EVENT_TYPE_QUERY = Query(default=None, max_length=120)


@router.post(
    "/endpoints",
    response_model=WebhookEndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_endpoint(
    payload: WebhookEndpointCreateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> WebhookEndpointResponse:
    result = WebhookService(session).create_endpoint(actor=actor, payload=payload)
    return WebhookEndpointResponse.model_validate(result.endpoint, from_attributes=True)


@router.get("/endpoints", response_model=list[WebhookEndpointResponse])
async def list_webhook_endpoints(
    actor: CurrentActorDep,
    session: SessionDep,
) -> list[WebhookEndpointResponse]:
    endpoints = WebhookService(session).list_endpoints(actor=actor)
    return [
        WebhookEndpointResponse.model_validate(endpoint, from_attributes=True)
        for endpoint in endpoints
    ]


@router.patch("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse)
async def update_webhook_endpoint(
    endpoint_id: UUID,
    payload: WebhookEndpointUpdateRequest,
    actor: CurrentActorDep,
    session: SessionDep,
) -> WebhookEndpointResponse:
    result = WebhookService(session).update_endpoint(
        actor=actor,
        endpoint_id=endpoint_id,
        payload=payload,
    )
    return WebhookEndpointResponse.model_validate(result.endpoint, from_attributes=True)


@router.get("/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_webhook_deliveries(
    actor: CurrentActorDep,
    session: SessionDep,
    limit: int = LIMIT_QUERY,
    offset: int = OFFSET_QUERY,
    status: WebhookDeliveryStatus | None = STATUS_QUERY,
    event_type: str | None = EVENT_TYPE_QUERY,
) -> list[WebhookDeliveryResponse]:
    deliveries = WebhookService(session).list_deliveries(
        actor=actor,
        status=status,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return [
        WebhookDeliveryResponse.model_validate(delivery, from_attributes=True)
        for delivery in deliveries
    ]


@router.post("/deliveries/{delivery_id}/retry", response_model=WebhookDeliveryResponse)
async def retry_webhook_delivery(
    delivery_id: UUID,
    actor: CurrentActorDep,
    session: SessionDep,
) -> WebhookDeliveryResponse:
    delivery = WebhookService(session).retry_delivery(actor=actor, delivery_id=delivery_id)
    return WebhookDeliveryResponse.model_validate(delivery, from_attributes=True)
