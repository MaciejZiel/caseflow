"""Organization API key management and integration lookups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.v1.schemas.api_keys import ApiKeyCreateRequest
from app.application.actors import ActorContext
from app.application.services.events import EventPublisher
from app.core.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from app.domain.api_keys.models import ApiKey, ApiKeyScope
from app.domain.cases.models import Case, CaseStatus
from app.domain.documents.models import Document
from app.domain.organizations.models import OrganizationRole, OrganizationStatus
from app.domain.organizations.policies import ensure_role_allowed
from app.infrastructure.security.opaque_tokens import generate_opaque_token, hash_opaque_token

API_KEY_MANAGER_ROLES = frozenset({OrganizationRole.OWNER, OrganizationRole.ADMIN})


@dataclass(slots=True)
class ApiKeyCreateResult:
    api_key: ApiKey
    plaintext_key: str


@dataclass(slots=True)
class ApiKeyContext:
    api_key: ApiKey

    @property
    def organization(self):
        return self.api_key.organization

    @property
    def scopes(self) -> set[ApiKeyScope]:
        return {ApiKeyScope(scope) for scope in self.api_key.scopes_json}


class ApiKeyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.publisher = EventPublisher(session)

    def create_api_key(
        self,
        *,
        actor: ActorContext,
        payload: ApiKeyCreateRequest,
    ) -> ApiKeyCreateResult:
        self._ensure_api_key_manager(actor)
        plaintext_key = _generate_plaintext_api_key()
        api_key = ApiKey(
            organization_id=actor.organization.id,
            created_by_user_id=actor.user.id,
            name=payload.name,
            description=payload.description,
            key_prefix=plaintext_key[:16],
            key_hash=hash_opaque_token(plaintext_key),
            scopes_json=[scope.value for scope in payload.scopes],
            expires_at=payload.expires_at,
        )
        self.session.add(api_key)
        self.session.flush()
        self.publisher.record_event(
            organization_id=actor.organization.id,
            actor_user_id=actor.user.id,
            event_type="api_key.created",
            entity_type="api_key",
            entity_id=api_key.id,
            new_values={
                "name": api_key.name,
                "scopes": api_key.scopes_json,
                "expires_at": api_key.expires_at,
            },
            deliver_webhooks=False,
        )
        self.session.commit()
        self.session.refresh(api_key)
        return ApiKeyCreateResult(api_key=api_key, plaintext_key=plaintext_key)

    def list_api_keys(
        self,
        *,
        actor: ActorContext,
    ) -> list[ApiKey]:
        self._ensure_api_key_manager(actor)
        return list(
            self.session.scalars(
                select(ApiKey)
                .where(ApiKey.organization_id == actor.organization.id)
                .order_by(
                    ApiKey.revoked_at.is_not(None).asc(),
                    ApiKey.created_at.desc(),
                )
            )
        )

    def revoke_api_key(
        self,
        *,
        actor: ActorContext,
        api_key_id: UUID,
    ) -> ApiKey:
        self._ensure_api_key_manager(actor)
        api_key = self.session.scalar(
            select(ApiKey).where(
                ApiKey.id == api_key_id,
                ApiKey.organization_id == actor.organization.id,
            )
        )
        if api_key is None:
            raise NotFoundError("api_key", "API key does not exist.")
        if api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(UTC)
            api_key.revoke_reason = "manual_revoke"
            self.publisher.record_event(
                organization_id=actor.organization.id,
                actor_user_id=actor.user.id,
                event_type="api_key.revoked",
                entity_type="api_key",
                entity_id=api_key.id,
                old_values={"revoked_at": None},
                new_values={"revoked_at": api_key.revoked_at},
                deliver_webhooks=False,
            )
            self.session.commit()
        self.session.refresh(api_key)
        return api_key

    def authenticate_api_key(
        self,
        *,
        raw_key: str,
        client_ip: str | None,
        required_scopes: set[ApiKeyScope],
    ) -> ApiKeyContext:
        api_key = self.session.scalar(
            select(ApiKey)
            .options(joinedload(ApiKey.organization))
            .where(ApiKey.key_hash == hash_opaque_token(raw_key))
        )
        if api_key is None:
            raise AuthenticationError("API key is invalid or inactive.")
        if api_key.revoked_at is not None:
            raise AuthenticationError("API key is invalid or inactive.")
        if api_key.expires_at is not None and _to_utc(api_key.expires_at) <= datetime.now(UTC):
            raise AuthenticationError("API key is invalid or inactive.")
        if api_key.organization.status is not OrganizationStatus.ACTIVE:
            raise AuthenticationError("API key organization is not active.")

        granted_scopes = {ApiKeyScope(scope) for scope in api_key.scopes_json}
        missing_scopes = required_scopes - granted_scopes
        if missing_scopes:
            raise PermissionDeniedError("API key does not grant the required scope.")

        api_key.last_used_at = datetime.now(UTC)
        api_key.last_used_ip = client_ip
        self.session.commit()
        self.session.refresh(api_key)
        return ApiKeyContext(api_key=api_key)

    def list_cases_for_integration(
        self,
        *,
        api_key: ApiKeyContext,
        limit: int,
        status: CaseStatus | None = None,
        external_id: str | None = None,
        updated_after: datetime | None = None,
    ) -> list[Case]:
        query = (
            select(Case)
            .where(Case.organization_id == api_key.organization.id)
            .order_by(Case.updated_at.desc(), Case.created_at.desc())
            .limit(limit)
        )
        if status is not None:
            query = query.where(Case.status == status)
        if external_id is not None:
            query = query.where(Case.external_id == external_id)
        if updated_after is not None:
            query = query.where(Case.updated_at >= updated_after)
        return list(self.session.scalars(query))

    def get_case_for_integration(self, *, api_key: ApiKeyContext, case_id: UUID) -> Case:
        case = self.session.scalar(
            select(Case).where(
                Case.id == case_id,
                Case.organization_id == api_key.organization.id,
            )
        )
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        return case

    def list_case_documents_for_integration(
        self,
        *,
        api_key: ApiKeyContext,
        case_id: UUID,
    ) -> list[Document]:
        self.get_case_for_integration(api_key=api_key, case_id=case_id)
        return list(
            self.session.scalars(
                select(Document)
                .where(
                    Document.case_id == case_id,
                    Document.organization_id == api_key.organization.id,
                )
                .order_by(Document.created_at.desc())
            )
        )

    def get_document_for_integration(
        self,
        *,
        api_key: ApiKeyContext,
        document_id: UUID,
    ) -> Document:
        document = self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == api_key.organization.id,
            )
        )
        if document is None:
            raise NotFoundError("document", "Document does not exist.")
        return document

    def _ensure_api_key_manager(self, actor: ActorContext) -> None:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=API_KEY_MANAGER_ROLES,
            message="You do not have permission to manage API keys.",
        )


def _generate_plaintext_api_key() -> str:
    return f"cfk_{generate_opaque_token()}"


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
