"""Event publication into audit logs and webhook delivery outbox."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.audit.models import AuditLog
from app.domain.webhooks.models import WebhookDelivery, WebhookDeliveryStatus, WebhookEndpoint


class EventPublisher:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record_event(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID | None,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        old_values: dict[str, object] | None = None,
        new_values: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
        deliver_webhooks: bool = True,
    ) -> list[UUID]:
        occurred_at = datetime.now(UTC)
        audit_log = AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values_json=_to_jsonable(old_values),
            new_values_json=_to_jsonable(new_values),
            metadata_json=_to_jsonable(metadata),
        )
        self.session.add(audit_log)

        if not deliver_webhooks:
            return []

        endpoints = list(
            self.session.scalars(
                select(WebhookEndpoint).where(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.is_active.is_(True),
                )
            )
        )
        payload = {
            "event_type": event_type,
            "occurred_at": occurred_at,
            "organization_id": organization_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "actor_user_id": actor_user_id,
            "data": {
                "old_values": old_values,
                "new_values": new_values,
                "metadata": metadata,
            },
        }

        delivery_ids: list[UUID] = []
        for endpoint in endpoints:
            subscribed_event_types = set(endpoint.subscribed_event_types_json or [])
            if subscribed_event_types and event_type not in subscribed_event_types:
                continue
            delivery_id = uuid4()
            delivery = WebhookDelivery(
                id=delivery_id,
                organization_id=organization_id,
                endpoint_id=endpoint.id,
                event_type=event_type,
                status=WebhookDeliveryStatus.PENDING,
                request_body_json=_to_jsonable(payload) or {},
            )
            self.session.add(delivery)
            delivery_ids.append(delivery_id)
        return delivery_ids


def _to_jsonable(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_to_jsonable(item) for item in value]
    return value
