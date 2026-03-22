"""add case comments table"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_add_case_comments_table"
down_revision = "0006_add_audit_and_webhook_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_case_comments_author_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_case_comments_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_case_comments_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_comments")),
    )
    op.create_index(op.f("ix_case_comments_case_id"), "case_comments", ["case_id"], unique=False)
    op.create_index(
        op.f("ix_case_comments_created_at"),
        "case_comments",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_case_comments_organization_id"),
        "case_comments",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_case_comments_organization_id"), table_name="case_comments")
    op.drop_index(op.f("ix_case_comments_created_at"), table_name="case_comments")
    op.drop_index(op.f("ix_case_comments_case_id"), table_name="case_comments")
    op.drop_table("case_comments")
