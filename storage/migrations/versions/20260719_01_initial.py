"""Initial durable Restock workflow schema, frozen at revision one."""

from alembic import op
import sqlalchemy as sa


revision = "20260719_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("prava_account_ref", sa.String(255), nullable=False),
        sa.Column("monthly_cap", sa.Numeric(18, 2), nullable=False),
        sa.Column("per_item_cap", sa.Numeric(18, 2), nullable=False),
        sa.Column("per_transaction_cap", sa.Numeric(18, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tracked_items",
        sa.Column("item_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tracked_items_user_id", "tracked_items", ["user_id"])
    op.create_table(
        "workflow_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("tracked_items.item_id"), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("active_item_key", sa.String(36), nullable=True),
        sa.Column("trigger_reason", sa.String(80), nullable=False),
        sa.Column("proposed_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("merchant", sa.String(80), nullable=False),
        sa.Column("proposed_action", sa.String(40), nullable=True),
        sa.Column("quote", sa.JSON(), nullable=True),
        sa.Column("prava_intent_ref", sa.String(255), nullable=True),
        sa.Column("mandate_ref", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("modes", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("active_item_key", name="uq_active_item_workflow"),
    )
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])
    op.create_index("ix_workflow_runs_item_id", "workflow_runs", ["item_id"])
    op.create_index("ix_workflow_runs_state", "workflow_runs", ["state"])
    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.run_id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_run_id", "notifications", ["run_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_table(
        "notification_actions",
        sa.Column("action_id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.run_id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("adjusted_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notification_actions_run_id", "notification_actions", ["run_id"])
    op.create_index("ix_notification_actions_user_id", "notification_actions", ["user_id"])
    op.create_table(
        "transactions",
        sa.Column("transaction_id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.run_id"), nullable=False, unique=True),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("tracked_items.item_id"), nullable=False),
        sa.Column("mandate_ref", sa.String(255), nullable=False),
        sa.Column("merchant_order_id", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("execution_mode", sa.String(30), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transactions_item_id", "transactions", ["item_id"])
    op.create_table(
        "audit_entries",
        sa.Column("audit_id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("item_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("modes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_entries_run_id", "audit_entries", ["run_id"])
    op.create_index("ix_audit_entries_user_id", "audit_entries", ["user_id"])
    op.create_index("ix_audit_entries_event_type", "audit_entries", ["event_type"])
    op.create_table(
        "scheduler_leases",
        sa.Column("lease_name", sa.String(100), primary_key=True),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "scheduler_leases",
        "audit_entries",
        "transactions",
        "notification_actions",
        "notifications",
        "workflow_runs",
        "tracked_items",
        "users",
    ):
        op.drop_table(table)
