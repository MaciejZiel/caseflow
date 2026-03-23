"""add admin notification digest schedule"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0017_add_admin_notification_digest_schedule"
down_revision = "0016_add_admin_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_notification_preferences",
        sa.Column(
            "digest_schedule",
            sa.Enum(
                "disabled",
                "hourly",
                "daily",
                "weekly",
                name="admin_notification_digest_schedule",
                native_enum=False,
            ),
            nullable=False,
            server_default="disabled",
        ),
    )
    op.add_column(
        "admin_notification_preferences",
        sa.Column("digest_next_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "admin_notification_preferences",
        sa.Column("digest_last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_admin_notification_preferences_digest_next_due_at"),
        "admin_notification_preferences",
        ["digest_next_due_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_admin_notification_preferences_digest_next_due_at"),
        table_name="admin_notification_preferences",
    )
    op.drop_column("admin_notification_preferences", "digest_last_sent_at")
    op.drop_column("admin_notification_preferences", "digest_next_due_at")
    op.drop_column("admin_notification_preferences", "digest_schedule")
