"""Model registry imported by Alembic and runtime setup."""

from app.domain.organizations.models import Invitation, Organization, OrganizationMembership
from app.domain.users.models import User


def import_model_modules() -> None:
    _ = (Organization, OrganizationMembership, Invitation, User)
