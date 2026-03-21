"""Model registry imported by Alembic and runtime setup."""

from app.domain.cases.models import Case
from app.domain.documents.models import Document, DocumentReview, DocumentVersion
from app.domain.jobs.models import ProcessingJob
from app.domain.organizations.models import Invitation, Organization, OrganizationMembership
from app.domain.users.models import User


def import_model_modules() -> None:
    _ = (
        Case,
        Document,
        DocumentReview,
        DocumentVersion,
        ProcessingJob,
        Organization,
        OrganizationMembership,
        Invitation,
        User,
    )
