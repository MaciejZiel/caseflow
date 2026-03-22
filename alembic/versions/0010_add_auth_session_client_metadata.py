"""add auth session client metadata"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_add_auth_session_client_metadata"
down_revision = "0009_add_processing_job_retry_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("client_ip", sa.String(length=64), nullable=True))
    op.add_column("auth_sessions", sa.Column("user_agent", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_sessions", "user_agent")
    op.drop_column("auth_sessions", "client_ip")
