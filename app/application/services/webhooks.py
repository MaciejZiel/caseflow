"""Webhook endpoint management and delivery dispatch services."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib import error, request
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.webhooks import (
    WebhookEndpointCreateRequest,
    WebhookEndpointUpdateRequest,
)
from app.application.actors import ActorContext
from app.application.services.events import EventPublisher
from app.core.errors import NotFoundError
from app.domain.organizations.models import OrganizationRole
from app.domain.organizations.policies import ensure_role_allowed
from app.domain.webhooks.models import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint

WEBHOOK_MANAGER_ROLES = frozenset({OrganizationRole.OWNER, OrganizationRole.ADMIN})


@dataclass(slots=True)
class WebhookMutationResult:
    endpoint: WebhookEndpoint
    delivery_ids: list[UUID]


class WebhookService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.publisher = EventPublisher(session)

    def create_endpoint(
        self,
        *,
        actor: ActorContext,
        payload: WebhookEndpointCreateRequest,
    ) -> WebhookMutationResult:
        self._ensure_manage_permission(actor)

        endpoint = WebhookEndpoint(
            organization_id=actor.organization.id,
            target_url=payload.target_url,
            signing_secret=payload.signing_secret or secrets.token_urlsafe(32),
            is_active=payload.is_active,
            created_by=actor.user.id,
        )
        self.session.add(endpoint)
        self.session.flush()
        delivery_ids = self.publisher.record_event(
            organization_id=actor.organization.id,
            actor_user_id=actor.user.id,
            event_type="webhook.created",
            entity_type="webhook_endpoint",
            entity_id=endpoint.id,
            new_values={
                "target_url": endpoint.target_url,
                "is_active": endpoint.is_active,
            },
            deliver_webhooks=False,
        )
        self.session.commit()
        self.session.refresh(endpoint)
        return WebhookMutationResult(endpoint=endpoint, delivery_ids=delivery_ids)

    def list_endpoints(self, *, actor: ActorContext) -> list[WebhookEndpoint]:
        self._ensure_manage_permission(actor)
        return list(
            self.session.scalars(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.organization_id == actor.organization.id)
                .order_by(WebhookEndpoint.created_at.asc())
            )
        )

    def update_endpoint(
        self,
        *,
        actor: ActorContext,
        endpoint_id: UUID,
        payload: WebhookEndpointUpdateRequest,
    ) -> WebhookMutationResult:
        self._ensure_manage_permission(actor)
        endpoint = self._get_endpoint_for_actor(actor=actor, endpoint_id=endpoint_id)
        if endpoint is None:
            raise NotFoundError("webhook_endpoint", "Webhook endpoint does not exist.")

        old_values = {
            "target_url": endpoint.target_url,
            "is_active": endpoint.is_active,
        }
        if payload.target_url is not None:
            endpoint.target_url = payload.target_url
        if payload.signing_secret is not None:
            endpoint.signing_secret = payload.signing_secret
        if payload.is_active is not None:
            endpoint.is_active = payload.is_active

        delivery_ids = self.publisher.record_event(
            organization_id=actor.organization.id,
            actor_user_id=actor.user.id,
            event_type="webhook.updated",
            entity_type="webhook_endpoint",
            entity_id=endpoint.id,
            old_values=old_values,
            new_values={
                "target_url": endpoint.target_url,
                "is_active": endpoint.is_active,
            },
            deliver_webhooks=False,
        )
        self.session.commit()
        self.session.refresh(endpoint)
        return WebhookMutationResult(endpoint=endpoint, delivery_ids=delivery_ids)

    def list_deliveries(
        self,
        *,
        actor: ActorContext,
        status: WebhookDeliveryStatus | None,
        event_type: str | None,
        limit: int,
        offset: int,
    ) -> list[WebhookDelivery]:
        self._ensure_manage_permission(actor)
        query = (
            select(WebhookDelivery)
            .where(WebhookDelivery.organization_id == actor.organization.id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            query = query.where(WebhookDelivery.status == status)
        if event_type is not None:
            query = query.where(WebhookDelivery.event_type == event_type)
        return list(self.session.scalars(query))

    def dispatch_deliveries(self, delivery_ids: list[UUID]) -> None:
        if not delivery_ids:
            return

        deliveries = list(
            self.session.scalars(
                select(WebhookDelivery)
                .where(WebhookDelivery.id.in_(delivery_ids))
                .order_by(WebhookDelivery.created_at.asc())
            )
        )
        for delivery in deliveries:
            endpoint = self.session.scalar(
                select(WebhookEndpoint).where(WebhookEndpoint.id == delivery.endpoint_id)
            )
            if endpoint is None:
                continue
            self._dispatch_single_delivery(delivery=delivery, endpoint=endpoint)

    def _dispatch_single_delivery(
        self,
        *,
        delivery: WebhookDelivery,
        endpoint: WebhookEndpoint,
    ) -> None:
        payload_bytes = json.dumps(
            delivery.request_body_json,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(
            endpoint.signing_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        delivery.attempts += 1

        req = request.Request(
            endpoint.target_url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "caseflow-webhook-dispatcher/1.0",
                "X-CaseFlow-Event": delivery.event_type,
                "X-CaseFlow-Signature": signature,
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=2) as response:  # noqa: S310
                body_excerpt = response.read(1000).decode("utf-8", errors="replace")
                delivery.status = WebhookDeliveryStatus.DELIVERED
                delivery.http_status = response.status
                delivery.response_body_excerpt = body_excerpt
                delivery.delivered_at = datetime.now(UTC)
                delivery.next_retry_at = None
        except error.HTTPError as exc:
            body_excerpt = exc.read(1000).decode("utf-8", errors="replace")
            self._mark_delivery_failed(
                delivery=delivery,
                http_status=exc.code,
                response_body_excerpt=body_excerpt,
            )
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            self._mark_delivery_failed(
                delivery=delivery,
                http_status=None,
                response_body_excerpt=str(exc)[:1000],
            )

        self.session.commit()

    def _mark_delivery_failed(
        self,
        *,
        delivery: WebhookDelivery,
        http_status: int | None,
        response_body_excerpt: str | None,
    ) -> None:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.http_status = http_status
        delivery.response_body_excerpt = response_body_excerpt
        delivery.next_retry_at = datetime.now(UTC) + timedelta(
            seconds=30 * (2 ** max(delivery.attempts - 1, 0))
        )

    def _ensure_manage_permission(self, actor: ActorContext) -> None:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=WEBHOOK_MANAGER_ROLES,
            message="Only owners and admins can manage webhooks.",
        )

    def _get_endpoint_for_actor(
        self,
        *,
        actor: ActorContext,
        endpoint_id: UUID,
    ) -> WebhookEndpoint | None:
        return self.session.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id,
                WebhookEndpoint.organization_id == actor.organization.id,
            )
        )
