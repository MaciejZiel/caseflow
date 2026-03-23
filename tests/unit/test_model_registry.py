from app.infrastructure.db.base import Base
from app.infrastructure.db.models import import_model_modules


def test_core_identity_tables_are_registered() -> None:
    import_model_modules()

    assert "admin_notifications" in Base.metadata.tables
    assert "admin_notification_preferences" in Base.metadata.tables
    assert "admin_organization_reviews" in Base.metadata.tables
    assert "admin_organization_review_comments" in Base.metadata.tables
    assert "organizations" in Base.metadata.tables
    assert "users" in Base.metadata.tables
    assert "auth_sessions" in Base.metadata.tables
    assert "api_keys" in Base.metadata.tables
    assert "password_reset_tokens" in Base.metadata.tables
    assert "organization_memberships" in Base.metadata.tables
    assert "invitations" in Base.metadata.tables
    assert "cases" in Base.metadata.tables
    assert "case_comments" in Base.metadata.tables
    assert "documents" in Base.metadata.tables
    assert "document_versions" in Base.metadata.tables
    assert "document_reviews" in Base.metadata.tables
    assert "outbound_emails" in Base.metadata.tables
    assert "processing_jobs" in Base.metadata.tables
    assert "audit_logs" in Base.metadata.tables
    assert "webhook_endpoints" in Base.metadata.tables
    assert "webhook_deliveries" in Base.metadata.tables
