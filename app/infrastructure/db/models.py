"""Model registry imported by Alembic and runtime setup."""

from app.domain.api_keys.models import ApiKey
from app.domain.audit.models import AuditLog
from app.domain.auth.models import AuthSession, PasswordResetToken
from app.domain.cases.models import Case, CaseComment
from app.domain.documents.models import Document, DocumentReview, DocumentVersion
from app.domain.emails.models import OutboundEmail
from app.domain.jobs.models import ProcessingJob
from app.domain.organizations.models import Invitation, Organization, OrganizationMembership
from app.domain.users.models import User
from app.domain.webhooks.models import WebhookDelivery, WebhookEndpoint


def import_model_modules() -> None:
    _ = (
        AuthSession,
        PasswordResetToken,
        ApiKey,
        Case,
        CaseComment,
        Document,
        DocumentReview,
        DocumentVersion,
        OutboundEmail,
        ProcessingJob,
        AuditLog,
        Organization,
        OrganizationMembership,
        Invitation,
        User,
        WebhookEndpoint,
        WebhookDelivery,
    )
