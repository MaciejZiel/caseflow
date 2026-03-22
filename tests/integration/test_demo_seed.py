from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.domain.cases.models import Case, CaseStatus
from app.domain.documents.models import Document, DocumentStatus, DocumentVersion
from app.domain.organizations.models import Organization, OrganizationMembership
from app.domain.users.models import User
from app.domain.webhooks.models import WebhookEndpoint
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import import_model_modules
from app.infrastructure.db.session import get_engine, get_session_factory, reset_db_state
from scripts.seed_demo_data import DEMO_ORGANIZATION_SLUG, seed_demo_data


def test_seed_demo_data_creates_realistic_workspace(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "caseflow-seed.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("TEST_DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-32-plus-bytes")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))

    get_settings.cache_clear()
    reset_db_state()
    import_model_modules()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    session = get_session_factory()()
    try:
        result = seed_demo_data(session)

        organization = session.scalar(
            select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG)
        )
        memberships = list(session.scalars(select(OrganizationMembership)))
        cases = list(session.scalars(select(Case).order_by(Case.external_id.asc())))
        documents = list(session.scalars(select(Document)))
        document_versions = list(session.scalars(select(DocumentVersion)))
        users = list(session.scalars(select(User)))
        webhook_endpoints = list(session.scalars(select(WebhookEndpoint)))

        assert organization is not None
        assert result.organization_slug == DEMO_ORGANIZATION_SLUG
        assert len(result.users) == 4
        assert len(result.cases) == 4
        assert len(users) == 4
        assert len(memberships) == 4
        assert len(cases) == 4
        assert len(documents) == 3
        assert len(document_versions) == 4
        assert len(webhook_endpoints) == 1
        assert webhook_endpoints[0].is_active is False
        assert {case.status for case in cases} == {
            CaseStatus.APPROVED,
            CaseStatus.REJECTED,
            CaseStatus.WAITING_FOR_DOCUMENTS,
            CaseStatus.ARCHIVED,
        }
        assert {document.status for document in documents} == {
            DocumentStatus.APPROVED,
            DocumentStatus.REJECTED,
            DocumentStatus.FAILED,
        }
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        reset_db_state()
        get_settings.cache_clear()
