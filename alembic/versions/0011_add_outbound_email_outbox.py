"""add outbound email outbox"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_add_outbound_email_outbox"
down_revision = "0010_add_auth_session_client_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbound_emails",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("template_key", sa.String(length=120), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "sent", "failed", name="outbound_email_status", native_enum=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("delivery_reference", sa.String(length=500), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_outbound_emails_organization_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_emails")),
    )
    op.create_index(
        op.f("ix_outbound_emails_created_at"),
        "outbound_emails",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_emails_organization_id"),
        "outbound_emails",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_emails_recipient_email"),
        "outbound_emails",
        ["recipient_email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_emails_status"),
        "outbound_emails",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_emails_template_key"),
        "outbound_emails",
        ["template_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_outbound_emails_template_key"), table_name="outbound_emails")
    op.drop_index(op.f("ix_outbound_emails_status"), table_name="outbound_emails")
    op.drop_index(op.f("ix_outbound_emails_recipient_email"), table_name="outbound_emails")
    op.drop_index(op.f("ix_outbound_emails_organization_id"), table_name="outbound_emails")
    op.drop_index(op.f("ix_outbound_emails_created_at"), table_name="outbound_emails")
    op.drop_table("outbound_emails")
