"""add auth session activity tracking"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_add_auth_session_activity_tracking"
down_revision = "0011_add_outbound_email_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("device_name", sa.String(length=120), nullable=True))
    op.add_column("auth_sessions", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.add_column("auth_sessions", sa.Column("last_seen_ip", sa.String(length=64), nullable=True))
    op.add_column(
        "auth_sessions",
        sa.Column("last_seen_user_agent", sa.String(length=255), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE auth_sessions
            SET last_seen_at = COALESCE(last_refreshed_at, created_at),
                last_seen_ip = client_ip,
                last_seen_user_agent = user_agent
            WHERE last_seen_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "last_seen_user_agent")
    op.drop_column("auth_sessions", "last_seen_ip")
    op.drop_column("auth_sessions", "last_seen_at")
    op.drop_column("auth_sessions", "device_name")
