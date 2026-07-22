"""Add non-secret durable merchant checkout attempt state."""

from alembic import op
import sqlalchemy as sa


revision = "20260722_05"
down_revision = "20260722_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merchant_checkout_attempts",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("merchant", sa.String(80), nullable=False),
        sa.Column("merchant_sku_id", sa.String(255), nullable=False),
        sa.Column("expected_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("merchant_order_id", sa.String(255), nullable=True),
        sa.Column("merchant_order_code", sa.String(255), nullable=True),
        sa.Column("prava_session_id", sa.String(255), nullable=True),
        sa.Column("prava_txn_ref_id", sa.String(255), nullable=True),
        sa.Column("credential_exposed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("credential_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("report_status", sa.String(10), nullable=True),
        sa.Column("report_state", sa.String(30), nullable=False, server_default="not_required"),
        sa.Column("report_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prava_reported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_merchant_checkout_attempts_merchant",
        "merchant_checkout_attempts",
        ["merchant"],
    )
    op.create_index(
        "ix_merchant_checkout_attempts_state",
        "merchant_checkout_attempts",
        ["state"],
    )
    op.create_index(
        "ix_merchant_checkout_attempts_report_state",
        "merchant_checkout_attempts",
        ["report_state"],
    )


def downgrade() -> None:
    op.drop_table("merchant_checkout_attempts")
