"""add admin review workflow tables"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_add_admin_review_workflow"
down_revision = "0014_add_webhook_subscriptions_and_replay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_organization_reviews",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "in_progress",
                "resolved",
                "dismissed",
                name="admin_review_status",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "low",
                "normal",
                "high",
                "urgent",
                name="admin_review_priority",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_score_snapshot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "risk_level_snapshot",
            sa.String(length=20),
            nullable=False,
            server_default="healthy",
        ),
        sa.Column("anomaly_count_snapshot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "top_anomaly_codes_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
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
            ["assigned_to_user_id"],
            ["users.id"],
            name=op.f("fk_admin_organization_reviews_assigned_to_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_admin_organization_reviews_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_admin_organization_reviews_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_organization_reviews")),
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_assigned_to_user_id"),
        "admin_organization_reviews",
        ["assigned_to_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_created_at"),
        "admin_organization_reviews",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_created_by_user_id"),
        "admin_organization_reviews",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_due_at"),
        "admin_organization_reviews",
        ["due_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_organization_id"),
        "admin_organization_reviews",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_priority"),
        "admin_organization_reviews",
        ["priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_status"),
        "admin_organization_reviews",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_reviews_updated_at"),
        "admin_organization_reviews",
        ["updated_at"],
        unique=False,
    )

    op.create_table(
        "admin_organization_review_comments",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_admin_organization_review_comments_author_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_admin_organization_review_comments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["admin_organization_reviews.id"],
            name=op.f(
                "fk_admin_organization_review_comments_review_id_admin_organization_reviews"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_organization_review_comments")),
    )
    op.create_index(
        op.f("ix_admin_organization_review_comments_author_user_id"),
        "admin_organization_review_comments",
        ["author_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_review_comments_created_at"),
        "admin_organization_review_comments",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_review_comments_organization_id"),
        "admin_organization_review_comments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_review_comments_review_id"),
        "admin_organization_review_comments",
        ["review_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_organization_review_comments_updated_at"),
        "admin_organization_review_comments",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_admin_organization_review_comments_updated_at"),
        table_name="admin_organization_review_comments",
    )
    op.drop_index(
        op.f("ix_admin_organization_review_comments_review_id"),
        table_name="admin_organization_review_comments",
    )
    op.drop_index(
        op.f("ix_admin_organization_review_comments_organization_id"),
        table_name="admin_organization_review_comments",
    )
    op.drop_index(
        op.f("ix_admin_organization_review_comments_created_at"),
        table_name="admin_organization_review_comments",
    )
    op.drop_index(
        op.f("ix_admin_organization_review_comments_author_user_id"),
        table_name="admin_organization_review_comments",
    )
    op.drop_table("admin_organization_review_comments")

    op.drop_index(
        op.f("ix_admin_organization_reviews_updated_at"),
        table_name="admin_organization_reviews",
    )
    op.drop_index(
        op.f("ix_admin_organization_reviews_status"),
        table_name="admin_organization_reviews",
    )
    op.drop_index(
        op.f("ix_admin_organization_reviews_priority"),
        table_name="admin_organization_reviews",
    )
    op.drop_index(
        op.f("ix_admin_organization_reviews_organization_id"),
        table_name="admin_organization_reviews",
    )
    op.drop_index(
        op.f("ix_admin_organization_reviews_due_at"),
        table_name="admin_organization_reviews",
    )
    op.drop_index(
        op.f("ix_admin_organization_reviews_created_by_user_id"),
        table_name="admin_organization_reviews",
    )
    op.drop_index(
        op.f("ix_admin_organization_reviews_created_at"),
        table_name="admin_organization_reviews",
    )
    op.drop_index(
        op.f("ix_admin_organization_reviews_assigned_to_user_id"),
        table_name="admin_organization_reviews",
    )
    op.drop_table("admin_organization_reviews")
