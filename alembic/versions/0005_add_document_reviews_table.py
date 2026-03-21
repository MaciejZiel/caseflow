"""add document reviews table"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_add_document_reviews_table"
down_revision = "0004_add_documents_and_jobs_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "decision",
            sa.Enum(
                "approved",
                "rejected",
                name="document_review_decision",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_reviews_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_document_reviews_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name=op.f("fk_document_reviews_reviewer_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_reviews")),
    )
    op.create_index(
        op.f("ix_document_reviews_created_at"),
        "document_reviews",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_reviews_document_id"),
        "document_reviews",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_reviews_organization_id"),
        "document_reviews",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_reviews_organization_id"), table_name="document_reviews")
    op.drop_index(op.f("ix_document_reviews_document_id"), table_name="document_reviews")
    op.drop_index(op.f("ix_document_reviews_created_at"), table_name="document_reviews")
    op.drop_table("document_reviews")
