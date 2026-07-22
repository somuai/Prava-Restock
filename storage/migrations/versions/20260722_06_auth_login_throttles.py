"""Add durable login throttling shared by production API replicas."""

from alembic import op
import sqlalchemy as sa


revision = "20260722_06"
down_revision = "20260722_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_login_throttles",
        sa.Column("source_hash", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_auth_login_throttles_window_started_at",
        "auth_login_throttles",
        ["window_started_at"],
    )


def downgrade() -> None:
    op.drop_table("auth_login_throttles")
