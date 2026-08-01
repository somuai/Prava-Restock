"""Add public pilot waitlist leads.

Revision ID: 20260730_09
Revises: 20260730_08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_09"
down_revision = "20260730_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waitlist_leads",
        sa.Column("lead_id", sa.String(36), primary_key=True),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("track_interest", sa.String(20), nullable=True),
        sa.Column("first_use_category", sa.String(80), nullable=True),
        sa.Column("preferred_channel", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "pilot_email_consent_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("research_opt_in", sa.Boolean(), nullable=False),
        sa.Column("privacy_notice_version", sa.String(40), nullable=False),
        sa.Column("landing_variant", sa.String(80), nullable=True),
        sa.Column("entry_demo_track", sa.String(20), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(100), nullable=True),
        sa.Column("referrer_host", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_waitlist_leads_email_normalized",
        "waitlist_leads",
        ["email_normalized"],
        unique=True,
    )
    op.create_index(
        "ix_waitlist_leads_status",
        "waitlist_leads",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_waitlist_leads_status", table_name="waitlist_leads"
    )
    op.drop_index(
        "ix_waitlist_leads_email_normalized", table_name="waitlist_leads"
    )
    op.drop_table("waitlist_leads")
