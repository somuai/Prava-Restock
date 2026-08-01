"""Add durable external authentication identities.

Revision ID: 20260730_08
Revises: 20260722_07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_08"
down_revision = "20260722_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("identity_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "subject", name="uq_auth_identity_subject"
        ),
        sa.UniqueConstraint(
            "user_id", "provider", name="uq_user_auth_provider"
        ),
    )
    op.create_index(
        "ix_auth_identities_user_id", "auth_identities", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_table("auth_identities")
