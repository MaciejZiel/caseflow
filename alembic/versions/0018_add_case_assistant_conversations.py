"""add case assistant conversations"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0018_add_case_assistant_conversations"
down_revision = "0017_add_admin_notification_digest_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "prompt_mode",
            sa.Enum(
                "general",
                "case_summary",
                "review_assistant",
                "next_actions",
                name="assistant_prompt_mode",
                native_enum=False,
            ),
            nullable=False,
            server_default="general",
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_conversations")),
    )
    op.create_index(
        op.f("ix_assistant_conversations_case_id"),
        "assistant_conversations",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_conversations_created_at"),
        "assistant_conversations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_conversations_organization_id"),
        "assistant_conversations",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "assistant_messages",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "user",
                "assistant",
                name="assistant_message_role",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "prompt_mode",
            sa.Enum(
                "general",
                "case_summary",
                "review_assistant",
                "next_actions",
                name="assistant_prompt_mode",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["assistant_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_messages")),
    )
    op.create_index(
        op.f("ix_assistant_messages_case_id"),
        "assistant_messages",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_messages_conversation_id"),
        "assistant_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_messages_created_at"),
        "assistant_messages",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_messages_organization_id"),
        "assistant_messages",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_messages_organization_id"), table_name="assistant_messages")
    op.drop_index(op.f("ix_assistant_messages_created_at"), table_name="assistant_messages")
    op.drop_index(op.f("ix_assistant_messages_conversation_id"), table_name="assistant_messages")
    op.drop_index(op.f("ix_assistant_messages_case_id"), table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index(
        op.f("ix_assistant_conversations_organization_id"),
        table_name="assistant_conversations",
    )
    op.drop_index(
        op.f("ix_assistant_conversations_created_at"),
        table_name="assistant_conversations",
    )
    op.drop_index(op.f("ix_assistant_conversations_case_id"), table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
