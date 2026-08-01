"""Add durable waitlist welcome-email outbox.

Revision ID: 20260801_11
Revises: 20260801_10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_11"
down_revision = "20260801_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waitlist_welcome_emails",
        sa.Column("delivery_id", sa.String(36), primary_key=True),
        sa.Column(
            "lead_id",
            sa.String(36),
            sa.ForeignKey("waitlist_leads.lead_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_owner", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'failed', 'sending', 'sent')",
            name="ck_waitlist_welcome_email_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_waitlist_welcome_email_attempts_nonnegative",
        ),
    )
    op.create_index(
        "ix_waitlist_welcome_emails_status",
        "waitlist_welcome_emails",
        ["status"],
    )
    # Existing consenting leads should receive the same durable pending state.
    # Reusing lead_id here is collision-safe because this is a separate table.
    op.execute(
        "INSERT INTO waitlist_welcome_emails "
        "(delivery_id, lead_id, status, attempts, last_attempted_at, "
        "claim_owner, lease_expires_at, sent_at, "
        "last_error, created_at, updated_at) "
        "SELECT lead_id, lead_id, 'pending', 0, NULL, NULL, NULL, NULL, NULL, "
        "created_at, updated_at FROM waitlist_leads"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_waitlist_welcome_emails_status",
        table_name="waitlist_welcome_emails",
    )
    op.drop_table("waitlist_welcome_emails")
