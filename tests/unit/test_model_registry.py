from app.infrastructure.db.base import Base
from app.infrastructure.db.models import import_model_modules


def test_core_identity_tables_are_registered() -> None:
    import_model_modules()

    assert "organizations" in Base.metadata.tables
    assert "users" in Base.metadata.tables
    assert "organization_memberships" in Base.metadata.tables
    assert "invitations" in Base.metadata.tables
