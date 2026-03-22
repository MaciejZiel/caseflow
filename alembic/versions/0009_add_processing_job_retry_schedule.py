"""add processing job retry schedule"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_add_processing_job_retry_schedule"
down_revision = "0008_add_auth_sessions_and_password_resets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_processing_jobs_next_retry_at"),
        "processing_jobs",
        ["next_retry_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_jobs_next_retry_at"), table_name="processing_jobs")
    op.drop_column("processing_jobs", "next_retry_at")
