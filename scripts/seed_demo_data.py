"""Seed a local demo workspace with realistic CaseFlow data."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.auth import RegistrationRequest
from app.api.v1.schemas.cases import CaseCommentCreateRequest, CaseCreateRequest
from app.api.v1.schemas.documents import (
    DocumentApproveRequest,
    DocumentRejectRequest,
    DocumentUploadRequest,
    DocumentVersionUploadRequest,
)
from app.api.v1.schemas.organizations import InvitationAcceptRequest, InvitationCreateRequest
from app.api.v1.schemas.webhooks import WebhookEndpointCreateRequest
from app.application.actors import ActorContext
from app.application.services.auth import AuthService
from app.application.services.cases import CaseService
from app.application.services.documents import DocumentService
from app.application.services.invitations import InvitationService
from app.application.services.webhooks import WebhookService
from app.core.config import get_settings
from app.core.errors import ConflictError
from app.domain.cases.models import CasePriority
from app.domain.documents.models import DocumentType
from app.domain.organizations.models import Organization, OrganizationRole
from app.domain.users.models import User
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.storage.local import LocalFileStorage

DEMO_ORGANIZATION_NAME = "CaseFlow Demo Claims"
DEMO_ORGANIZATION_SLUG = "demo-claims"
DEMO_WEBHOOK_TARGET_URL = "https://example.invalid/caseflow-demo"
DEMO_WEBHOOK_SIGNING_SECRET = "caseflow-demo-signing-secret-12345"


@dataclass(frozen=True, slots=True)
class DemoUserProfile:
    role: OrganizationRole
    first_name: str
    last_name: str
    email: str
    password: str


@dataclass(slots=True)
class DemoCaseSummary:
    external_id: str
    title: str
    status: str


@dataclass(slots=True)
class DemoSeedResult:
    organization_slug: str
    storage_path: str
    users: list[dict[str, str]]
    cases: list[DemoCaseSummary]
    webhook_target_url: str


DEMO_USERS = (
    DemoUserProfile(
        role=OrganizationRole.OWNER,
        first_name="Ada",
        last_name="Lovelace",
        email="demo.owner@caseflow.local",
        password="OwnerPass123",
    ),
    DemoUserProfile(
        role=OrganizationRole.ADMIN,
        first_name="Grace",
        last_name="Hopper",
        email="demo.admin@caseflow.local",
        password="AdminPass123",
    ),
    DemoUserProfile(
        role=OrganizationRole.REVIEWER,
        first_name="Joan",
        last_name="Clarke",
        email="demo.reviewer@caseflow.local",
        password="ReviewerPass123",
    ),
    DemoUserProfile(
        role=OrganizationRole.MEMBER,
        first_name="Margaret",
        last_name="Hamilton",
        email="demo.member@caseflow.local",
        password="MemberPass123",
    ),
)


def seed_demo_data(
    session: Session,
    *,
    storage: LocalFileStorage | None = None,
    replace_existing: bool = False,
) -> DemoSeedResult:
    storage = storage or LocalFileStorage()
    existing_organization = session.scalar(
        select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG)
    )
    existing_user = session.scalar(select(User).where(User.email.in_(_demo_emails())))
    if existing_organization is not None or existing_user is not None:
        if not replace_existing:
            raise ConflictError(
                "demo_dataset_exists",
                "Demo organization or one of the demo users already exists. "
                "Use --replace-existing to recreate it.",
            )
        _delete_existing_demo_dataset(session)

    owner_profile = DEMO_USERS[0]
    owner_result = AuthService(session).register_organization_owner(
        RegistrationRequest(
            organization_name=DEMO_ORGANIZATION_NAME,
            organization_slug=DEMO_ORGANIZATION_SLUG,
            first_name=owner_profile.first_name,
            last_name=owner_profile.last_name,
            email=owner_profile.email,
            password=owner_profile.password,
        )
    )
    owner_actor = ActorContext(user=owner_result.user, membership=owner_result.membership)

    actors = {owner_profile.role: owner_actor}
    invitation_service = InvitationService(session)
    for profile in DEMO_USERS[1:]:
        invitation = invitation_service.create_invitation(
            actor=owner_actor,
            payload=InvitationCreateRequest(email=profile.email, role=profile.role),
        )
        accepted = invitation_service.accept_invitation(
            InvitationAcceptRequest(
                token=invitation.invitation_token,
                first_name=profile.first_name,
                last_name=profile.last_name,
                password=profile.password,
            )
        )
        actors[profile.role] = ActorContext(user=accepted.user, membership=accepted.membership)

    WebhookService(session).create_endpoint(
        actor=owner_actor,
        payload=WebhookEndpointCreateRequest(
            target_url=DEMO_WEBHOOK_TARGET_URL,
            signing_secret=DEMO_WEBHOOK_SIGNING_SECRET,
            is_active=False,
        ),
    )

    case_service = CaseService(session)
    document_service = DocumentService(session, storage=storage)
    admin_actor = actors[OrganizationRole.ADMIN]
    reviewer_actor = actors[OrganizationRole.REVIEWER]
    member_actor = actors[OrganizationRole.MEMBER]

    approved_case = case_service.create_case(
        actor=admin_actor,
        payload=CaseCreateRequest(
            external_id="CF-1001",
            title="Approved motor claim",
            description="Rear-end collision claim with complete evidence package.",
            priority=CasePriority.HIGH,
            owner_user_id=member_actor.user.id,
            due_date=datetime.now(UTC) + timedelta(days=5),
        ),
    )
    case_service.create_comment(
        actor=admin_actor,
        case_id=approved_case.id,
        payload=CaseCommentCreateRequest(body="Initial case triage completed."),
    )
    first_document = document_service.create_document(
        actor=member_actor,
        case_id=approved_case.id,
        payload=_document_upload_request(
            title="Police report",
            document_type=DocumentType.STATEMENT,
            original_filename="police-report-v1.txt",
            content=b"Claim reference CF-1001\nVehicle inspected.\nAwaiting signatures.\n",
        ),
    )
    document_service.process_document_job(job_id=first_document.job.id)
    corrected_version = document_service.create_version(
        actor=member_actor,
        document_id=first_document.document.id,
        payload=_document_version_request(
            title="Police report",
            document_type=DocumentType.STATEMENT,
            original_filename="police-report-v2.txt",
            content=b"Claim reference CF-1001\nVehicle inspected.\nSignatures attached.\n",
        ),
    )
    document_service.process_document_job(job_id=corrected_version.job.id)
    document_service.approve_document(
        actor=reviewer_actor,
        document_id=first_document.document.id,
        payload=DocumentApproveRequest(reason="Evidence package is complete."),
    )
    case_service.create_comment(
        actor=reviewer_actor,
        case_id=approved_case.id,
        payload=CaseCommentCreateRequest(body="Approved after final document revision."),
    )

    rejected_case = case_service.create_case(
        actor=admin_actor,
        payload=CaseCreateRequest(
            external_id="CF-1002",
            title="Rejected invoice dispute",
            description="Submitted invoice does not match the insured event timeline.",
            priority=CasePriority.NORMAL,
            owner_user_id=member_actor.user.id,
            due_date=datetime.now(UTC) + timedelta(days=10),
        ),
    )
    rejected_document = document_service.create_document(
        actor=member_actor,
        case_id=rejected_case.id,
        payload=_document_upload_request(
            title="Repair invoice",
            document_type=DocumentType.INVOICE,
            original_filename="repair-invoice.txt",
            content=b"Invoice total: 9800 EUR\nService date mismatch noted.\n",
        ),
    )
    document_service.process_document_job(job_id=rejected_document.job.id)
    document_service.reject_document(
        actor=reviewer_actor,
        document_id=rejected_document.document.id,
        payload=DocumentRejectRequest(reason="Invoice date falls outside the covered incident."),
    )
    case_service.create_comment(
        actor=reviewer_actor,
        case_id=rejected_case.id,
        payload=CaseCommentCreateRequest(body="Rejection recorded with underwriting notes."),
    )

    failed_case = case_service.create_case(
        actor=member_actor,
        payload=CaseCreateRequest(
            external_id="CF-1003",
            title="Document processing failure demo",
            description="Shows a failed extraction path and retry-ready job history.",
            priority=CasePriority.URGENT,
            owner_user_id=member_actor.user.id,
            due_date=datetime.now(UTC) + timedelta(days=2),
        ),
    )
    failed_document = document_service.create_document(
        actor=member_actor,
        case_id=failed_case.id,
        payload=_document_upload_request(
            title="Corrupted attachment",
            document_type=DocumentType.OTHER,
            original_filename="corrupted-payload.txt",
            content=b"FAIL_PROCESSING\nSimulated invalid payload.\n",
        ),
    )
    document_service.process_document_job(job_id=failed_document.job.id)
    case_service.create_comment(
        actor=admin_actor,
        case_id=failed_case.id,
        payload=CaseCommentCreateRequest(body="Processing intentionally failed for demo purposes."),
    )

    archived_case = case_service.create_case(
        actor=owner_actor,
        payload=CaseCreateRequest(
            external_id="CF-1004",
            title="Archived historical case",
            description="Legacy demo case kept to illustrate archival state.",
            priority=CasePriority.LOW,
            owner_user_id=owner_actor.user.id,
            due_date=datetime.now(UTC) - timedelta(days=30),
        ),
    )
    case_service.create_comment(
        actor=owner_actor,
        case_id=archived_case.id,
        payload=CaseCommentCreateRequest(body="Closing historical demo record."),
    )
    case_service.archive_case(actor=owner_actor, case_id=archived_case.id)

    return DemoSeedResult(
        organization_slug=DEMO_ORGANIZATION_SLUG,
        storage_path=str(storage.base_path),
        users=[
            {
                "role": profile.role.value,
                "email": profile.email,
                "password": profile.password,
            }
            for profile in DEMO_USERS
        ],
        cases=[
            DemoCaseSummary(
                external_id=approved_case.external_id or "",
                title=approved_case.title,
                status=approved_case.status.value,
            ),
            DemoCaseSummary(
                external_id=rejected_case.external_id or "",
                title=rejected_case.title,
                status=rejected_case.status.value,
            ),
            DemoCaseSummary(
                external_id=failed_case.external_id or "",
                title=failed_case.title,
                status=failed_case.status.value,
            ),
            DemoCaseSummary(
                external_id=archived_case.external_id or "",
                title=archived_case.title,
                status=archived_case.status.value,
            ),
        ],
        webhook_target_url=DEMO_WEBHOOK_TARGET_URL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete the existing demo organization and demo users before reseeding.",
    )
    args = parser.parse_args()

    settings = get_settings()
    session = get_session_factory()()
    try:
        result = seed_demo_data(session, replace_existing=args.replace_existing)
    except ConflictError as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                    }
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()

    print(json.dumps(_serialize_result(result, settings.local_storage_path), indent=2))
    return 0


def _serialize_result(result: DemoSeedResult, default_storage_path: Path) -> dict[str, object]:
    return {
        "organization_slug": result.organization_slug,
        "storage_path": result.storage_path or str(default_storage_path),
        "users": result.users,
        "cases": [asdict(item) for item in result.cases],
        "webhook_target_url": result.webhook_target_url,
    }


def _document_upload_request(
    *,
    title: str,
    document_type: DocumentType,
    original_filename: str,
    content: bytes,
) -> DocumentUploadRequest:
    return DocumentUploadRequest(
        title=title,
        document_type=document_type,
        original_filename=original_filename,
        mime_type="text/plain",
        content_base64=_encode_content(content),
    )


def _document_version_request(
    *,
    title: str,
    document_type: DocumentType,
    original_filename: str,
    content: bytes,
) -> DocumentVersionUploadRequest:
    return DocumentVersionUploadRequest(
        title=title,
        document_type=document_type,
        original_filename=original_filename,
        mime_type="text/plain",
        content_base64=_encode_content(content),
    )


def _encode_content(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _demo_emails() -> tuple[str, ...]:
    return tuple(profile.email for profile in DEMO_USERS)


def _delete_existing_demo_dataset(session: Session) -> None:
    existing_organization = session.scalar(
        select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG)
    )
    if existing_organization is not None:
        session.delete(existing_organization)
        session.flush()

    existing_users = list(session.scalars(select(User).where(User.email.in_(_demo_emails()))))
    for user in existing_users:
        session.delete(user)
    session.commit()


if __name__ == "__main__":
    raise SystemExit(main())
