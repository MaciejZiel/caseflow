"""Tenant-scoped case application services."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.schemas.cases import CaseCreateRequest, CaseUpdateRequest
from app.application.actors import ActorContext
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.domain.cases.models import Case, CasePriority, CaseStatus
from app.domain.cases.policies import CASE_READ_ROLES, CASE_WRITE_ROLES
from app.domain.organizations.models import OrganizationMembership
from app.domain.organizations.policies import ensure_role_allowed


class CaseService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_case(self, *, actor: ActorContext, payload: CaseCreateRequest) -> Case:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=CASE_WRITE_ROLES,
            message="Your role cannot create cases.",
        )
        self._validate_case_owner(actor=actor, owner_user_id=payload.owner_user_id)

        case = Case(
            organization_id=actor.organization.id,
            external_id=payload.external_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            owner_user_id=payload.owner_user_id,
            created_by=actor.user.id,
            due_date=payload.due_date,
        )

        try:
            self.session.add(case)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "case_external_id_conflict",
                "A case with this external_id already exists in the organization.",
            ) from exc

        self.session.refresh(case)
        return case

    def list_cases(
        self,
        *,
        actor: ActorContext,
        limit: int,
        offset: int,
        status: CaseStatus | None,
        priority: CasePriority | None,
    ) -> list[Case]:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=CASE_READ_ROLES,
            message="Your role cannot view cases.",
        )

        query = (
            select(Case)
            .where(Case.organization_id == actor.organization.id)
            .order_by(Case.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            query = query.where(Case.status == status)
        if priority is not None:
            query = query.where(Case.priority == priority)
        return list(self.session.scalars(query))

    def get_case(self, *, actor: ActorContext, case_id: UUID) -> Case:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=CASE_READ_ROLES,
            message="Your role cannot view cases.",
        )
        case = self._get_case_for_actor(actor=actor, case_id=case_id)
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        return case

    def update_case(
        self,
        *,
        actor: ActorContext,
        case_id: UUID,
        payload: CaseUpdateRequest,
    ) -> Case:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=CASE_WRITE_ROLES,
            message="Your role cannot update cases.",
        )
        case = self._get_case_for_actor(actor=actor, case_id=case_id)
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        if case.archived_at is not None:
            raise DomainValidationError(
                "archived_case_update_forbidden",
                "Archived cases cannot be updated.",
            )

        if "owner_user_id" in payload.model_fields_set:
            self._validate_case_owner(actor=actor, owner_user_id=payload.owner_user_id)

        for field_name in payload.model_fields_set:
            if field_name not in {
                "title",
                "description",
                "external_id",
                "status",
                "priority",
                "owner_user_id",
                "due_date",
            }:
                continue
            value = getattr(payload, field_name)
            setattr(case, field_name, value)

        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError(
                "case_external_id_conflict",
                "A case with this external_id already exists in the organization.",
            ) from exc

        self.session.refresh(case)
        return case

    def archive_case(self, *, actor: ActorContext, case_id: UUID) -> Case:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=CASE_WRITE_ROLES,
            message="Your role cannot archive cases.",
        )
        case = self._get_case_for_actor(actor=actor, case_id=case_id)
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        if case.archived_at is not None:
            raise DomainValidationError(
                "case_already_archived",
                "Case has already been archived.",
            )

        case.archived_at = datetime.now(UTC)
        case.status = CaseStatus.ARCHIVED
        self.session.commit()
        self.session.refresh(case)
        return case

    def _get_case_for_actor(self, *, actor: ActorContext, case_id: UUID) -> Case | None:
        return self.session.scalar(
            select(Case).where(
                Case.id == case_id,
                Case.organization_id == actor.organization.id,
            )
        )

    def _validate_case_owner(self, *, actor: ActorContext, owner_user_id: UUID | None) -> None:
        if owner_user_id is None:
            return

        membership = self.session.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == actor.organization.id,
                OrganizationMembership.user_id == owner_user_id,
                OrganizationMembership.is_active.is_(True),
            )
        )
        if membership is None:
            raise DomainValidationError(
                "invalid_case_owner",
                "Selected case owner is not an active member of the organization.",
            )
