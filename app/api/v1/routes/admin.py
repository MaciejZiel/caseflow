"""Platform admin routes."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import SuperuserActor, get_current_superuser_actor
from app.api.v1.schemas.admin import (
    AdminAuditEventResponse,
    AdminFailureResponse,
    AdminOrganizationDetailResponse,
    AdminOrganizationListItemResponse,
    AdminOrganizationStatusChangeRequest,
    AdminOrganizationStatusChangeResponse,
    AdminOverviewResponse,
    AdminRetryDueResponse,
)
from app.api.v1.schemas.operations import OperationsFailureResponse
from app.application.services.admin import AdminService
from app.domain.organizations.models import OrganizationStatus
from app.infrastructure.db.session import get_db_session

router = APIRouter(prefix="/admin")
SessionDep = Annotated[Session, Depends(get_db_session)]
SuperuserActorDep = Annotated[SuperuserActor, Depends(get_current_superuser_actor)]


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_overview(
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminOverviewResponse:
    overview = AdminService(session).get_overview(actor=actor)
    return AdminOverviewResponse(
        total_organizations=overview.total_organizations,
        organizations_by_status=overview.organizations_by_status,
        active_auth_sessions=overview.active_auth_sessions,
        active_api_keys=overview.active_api_keys,
        open_cases=overview.open_cases,
        failed_jobs=overview.failed_jobs,
        failed_webhook_deliveries=overview.failed_webhook_deliveries,
        failed_emails=overview.failed_emails,
    )


@router.get("/failures", response_model=list[AdminFailureResponse])
async def list_recent_failures(
    actor: SuperuserActorDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    source: Annotated[
        Literal["processing_job", "webhook_delivery", "outbound_email"] | None,
        Query(),
    ] = None,
) -> list[AdminFailureResponse]:
    failures = AdminService(session).list_recent_failures(
        actor=actor,
        limit=limit,
        source=source,
    )
    return [
        AdminFailureResponse(
            organization_id=item.organization_id,
            organization_name=item.organization_name,
            organization_slug=item.organization_slug,
            source=item.source,
            id=item.id,
            status=item.status,
            summary=item.summary,
            reference_id=item.reference_id,
            reference_label=item.reference_label,
            attempts=item.attempts,
            last_error=item.last_error,
            next_retry_at=item.next_retry_at,
            created_at=item.created_at,
        )
        for item in failures
    ]


@router.post("/retry-due", response_model=AdminRetryDueResponse)
async def retry_due_items(
    actor: SuperuserActorDep,
    session: SessionDep,
    limit_per_queue: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AdminRetryDueResponse:
    result = AdminService(session).retry_due_items(
        actor=actor,
        limit_per_queue=limit_per_queue,
    )
    return AdminRetryDueResponse(
        processed_document_jobs=result.processed_document_jobs,
        processed_webhook_deliveries=result.processed_webhook_deliveries,
        processed_emails=result.processed_emails,
    )


@router.get("/organizations", response_model=list[AdminOrganizationListItemResponse])
async def list_organizations(
    actor: SuperuserActorDep,
    session: SessionDep,
    status: Annotated[OrganizationStatus | None, Query()] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AdminOrganizationListItemResponse]:
    organizations = AdminService(session).list_organizations(
        actor=actor,
        status=status,
        search=search,
        limit=limit,
    )
    return [
        AdminOrganizationListItemResponse(
            id=item.organization.id,
            name=item.organization.name,
            slug=item.organization.slug,
            status=item.organization.status,
            created_at=item.organization.created_at,
            updated_at=item.organization.updated_at,
            total_members=item.total_members,
            active_members=item.active_members,
            active_auth_sessions=item.active_auth_sessions,
            open_cases=item.open_cases,
            archived_cases=item.archived_cases,
            failed_jobs=item.failed_jobs,
            failed_webhook_deliveries=item.failed_webhook_deliveries,
            failed_emails=item.failed_emails,
            last_activity_at=item.last_activity_at,
        )
        for item in organizations
    ]


@router.get("/organizations/{organization_id}", response_model=AdminOrganizationDetailResponse)
async def get_organization_detail(
    organization_id: UUID,
    actor: SuperuserActorDep,
    session: SessionDep,
    failure_limit: Annotated[int, Query(ge=1, le=50)] = 10,
    audit_limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> AdminOrganizationDetailResponse:
    detail = AdminService(session).get_organization_detail(
        actor=actor,
        organization_id=organization_id,
        failure_limit=failure_limit,
        audit_limit=audit_limit,
    )
    return AdminOrganizationDetailResponse(
        organization=detail.organization,
        total_members=detail.total_members,
        active_members=detail.active_members,
        members_by_role=detail.members_by_role,
        active_api_keys=detail.active_api_keys,
        active_webhook_endpoints=detail.active_webhook_endpoints,
        active_auth_sessions=detail.active_auth_sessions,
        total_cases=detail.total_cases,
        open_cases=detail.open_cases,
        archived_cases=detail.archived_cases,
        total_documents=detail.total_documents,
        documents_by_status=detail.documents_by_status,
        jobs_by_status=detail.jobs_by_status,
        webhook_deliveries_by_status=detail.webhook_deliveries_by_status,
        emails_by_status=detail.emails_by_status,
        recent_failures=[
            OperationsFailureResponse(
                source=failure.source,
                id=failure.id,
                status=failure.status,
                summary=failure.summary,
                reference_id=failure.reference_id,
                reference_label=failure.reference_label,
                attempts=failure.attempts,
                last_error=failure.last_error,
                next_retry_at=failure.next_retry_at,
                created_at=failure.created_at,
            )
            for failure in detail.recent_failures
        ],
        recent_audit_events=[
            AdminAuditEventResponse(
                id=event.id,
                actor_user_id=event.actor_user_id,
                event_type=event.event_type,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                created_at=event.created_at,
            )
            for event in detail.recent_audit_events
        ],
        last_activity_at=detail.last_activity_at,
    )


@router.post(
    "/organizations/{organization_id}/suspend",
    response_model=AdminOrganizationStatusChangeResponse,
)
async def suspend_organization(
    organization_id: UUID,
    payload: AdminOrganizationStatusChangeRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminOrganizationStatusChangeResponse:
    result = AdminService(session).suspend_organization(
        actor=actor,
        organization_id=organization_id,
        reason=payload.reason,
    )
    return AdminOrganizationStatusChangeResponse(
        organization=result.organization,
        previous_status=result.previous_status,
        current_status=result.current_status,
        revoked_auth_sessions=result.revoked_auth_sessions,
        reason=result.reason,
    )


@router.post(
    "/organizations/{organization_id}/reactivate",
    response_model=AdminOrganizationStatusChangeResponse,
)
async def reactivate_organization(
    organization_id: UUID,
    payload: AdminOrganizationStatusChangeRequest,
    actor: SuperuserActorDep,
    session: SessionDep,
) -> AdminOrganizationStatusChangeResponse:
    result = AdminService(session).reactivate_organization(
        actor=actor,
        organization_id=organization_id,
        reason=payload.reason,
    )
    return AdminOrganizationStatusChangeResponse(
        organization=result.organization,
        previous_status=result.previous_status,
        current_status=result.current_status,
        revoked_auth_sessions=result.revoked_auth_sessions,
        reason=result.reason,
    )
