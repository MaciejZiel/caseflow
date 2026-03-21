"""add cases table"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_add_cases_table"
down_revision = "0002_add_invitations_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "in_review",
                "waiting_for_documents",
                "approved",
                "rejected",
                "archived",
                name="case_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "priority",
            sa.Enum(
                "low",
                "normal",
                "high",
                "urgent",
                name="case_priority",
                native_enum=False,
            ),
            nullable=False,
            server_default="normal",
        ),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_cases_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_cases_owner_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_cases_created_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.UniqueConstraint(
            "organization_id",
            "external_id",
            name=op.f("uq_cases_organization_id"),
        ),
    )
    op.create_index(op.f("ix_cases_created_at"), "cases", ["created_at"], unique=False)
    op.create_index(op.f("ix_cases_organization_id"), "cases", ["organization_id"], unique=False)
    op.create_index(op.f("ix_cases_status"), "cases", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cases_status"), table_name="cases")
    op.drop_index(op.f("ix_cases_organization_id"), table_name="cases")
    op.drop_index(op.f("ix_cases_created_at"), table_name="cases")
    op.drop_table("cases")
