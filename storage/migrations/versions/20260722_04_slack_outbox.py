"""Add the durable Slack notification delivery outbox."""

from alembic import op
import sqlalchemy as sa


revision = "20260722_04"
down_revision = "20260719_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_deliveries",
        sa.Column("delivery_id", sa.String(36), primary_key=True),
        sa.Column(
            "notification_id",
            sa.String(36),
            sa.ForeignKey("notifications.notification_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("workflow_runs.run_id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slack_message_ts", sa.String(40), nullable=True, unique=True),
        sa.Column("last_error", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_slack_deliveries_notification_id", "slack_deliveries", ["notification_id"])
    op.create_index("ix_slack_deliveries_run_id", "slack_deliveries", ["run_id"])
    op.create_index("ix_slack_deliveries_status", "slack_deliveries", ["status"])


def downgrade() -> None:
    op.drop_table("slack_deliveries")
