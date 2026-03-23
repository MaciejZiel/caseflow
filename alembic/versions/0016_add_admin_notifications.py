"""add admin notifications"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0016_add_admin_notifications"
down_revision = "0015_add_admin_review_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("review_id", sa.Uuid(), nullable=True),
        sa.Column(
            "notification_type",
            sa.Enum(
                "review_auto_opened",
                "review_overdue_escalated",
                name="admin_notification_type",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_admin_notifications_organization_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["admin_organization_reviews.id"],
            name=op.f("fk_admin_notifications_review_id_admin_organization_reviews"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_admin_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_notifications")),
    )
    op.create_index(
        op.f("ix_admin_notifications_created_at"),
        "admin_notifications",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_notifications_notification_type"),
        "admin_notifications",
        ["notification_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_notifications_organization_id"),
        "admin_notifications",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_notifications_read_at"),
        "admin_notifications",
        ["read_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_notifications_review_id"),
        "admin_notifications",
        ["review_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_notifications_user_id"),
        "admin_notifications",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "admin_notification_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "notify_on_review_auto_opened",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "notify_on_review_overdue_escalated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_admin_notification_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_notification_preferences")),
        sa.UniqueConstraint("user_id", name=op.f("uq_admin_notification_preferences_user_id")),
    )
    op.create_index(
        op.f("ix_admin_notification_preferences_created_at"),
        "admin_notification_preferences",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_notification_preferences_updated_at"),
        "admin_notification_preferences",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_notification_preferences_user_id"),
        "admin_notification_preferences",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_admin_notification_preferences_user_id"),
        table_name="admin_notification_preferences",
    )
    op.drop_index(
        op.f("ix_admin_notification_preferences_updated_at"),
        table_name="admin_notification_preferences",
    )
    op.drop_index(
        op.f("ix_admin_notification_preferences_created_at"),
        table_name="admin_notification_preferences",
    )
    op.drop_table("admin_notification_preferences")

    op.drop_index(op.f("ix_admin_notifications_user_id"), table_name="admin_notifications")
    op.drop_index(op.f("ix_admin_notifications_review_id"), table_name="admin_notifications")
    op.drop_index(op.f("ix_admin_notifications_read_at"), table_name="admin_notifications")
    op.drop_index(
        op.f("ix_admin_notifications_organization_id"),
        table_name="admin_notifications",
    )
    op.drop_index(
        op.f("ix_admin_notifications_notification_type"),
        table_name="admin_notifications",
    )
    op.drop_index(op.f("ix_admin_notifications_created_at"), table_name="admin_notifications")
    op.drop_table("admin_notifications")
