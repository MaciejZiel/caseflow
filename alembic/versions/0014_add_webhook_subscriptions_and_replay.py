"""add webhook subscriptions and replay tracking"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_add_webhook_subscriptions_and_replay"
down_revision = "0013_add_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("webhook_endpoints") as batch_op:
        batch_op.add_column(
            sa.Column(
                "subscribed_event_types_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )

    with op.batch_alter_table("webhook_deliveries") as batch_op:
        batch_op.add_column(sa.Column("replayed_from_delivery_id", sa.Uuid(), nullable=True))
        batch_op.create_index(
            op.f("ix_webhook_deliveries_replayed_from_delivery_id"),
            ["replayed_from_delivery_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            op.f("fk_webhook_deliveries_replayed_from_delivery_id_webhook_deliveries"),
            "webhook_deliveries",
            ["replayed_from_delivery_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("webhook_deliveries") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_webhook_deliveries_replayed_from_delivery_id_webhook_deliveries"),
            type_="foreignkey",
        )
        batch_op.drop_index(op.f("ix_webhook_deliveries_replayed_from_delivery_id"))
        batch_op.drop_column("replayed_from_delivery_id")

    with op.batch_alter_table("webhook_endpoints") as batch_op:
        batch_op.drop_column("subscribed_event_types_json")
