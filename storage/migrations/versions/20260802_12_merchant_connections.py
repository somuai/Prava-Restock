"""Add user-owned encrypted merchant OAuth connections.

Revision ID: 20260802_12
Revises: 20260801_11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260802_12"
down_revision = "20260801_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merchant_connections",
        sa.Column("connection_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("encrypted_tokens", sa.Text(), nullable=True),
        sa.Column("authorization_state_hash", sa.String(64), nullable=True),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=True),
        sa.Column("authorization_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_merchant_connection"),
        sa.UniqueConstraint("authorization_state_hash", name="uq_merchant_connection_state"),
        sa.CheckConstraint(
            "status IN ('not_connected', 'pending', 'connected', 'error', 'revoked')",
            name="ck_merchant_connection_status",
        ),
    )
    op.create_index(
        "ix_merchant_connections_user_id", "merchant_connections", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_merchant_connections_user_id", table_name="merchant_connections")
    op.drop_table("merchant_connections")
