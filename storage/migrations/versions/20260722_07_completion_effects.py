"""Add durable completion-effects work.

Revision ID: 20260722_07
Revises: 20260722_06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260722_07"
down_revision = "20260722_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "completion_effects",
        sa.Column("run_id", sa.String(36), sa.ForeignKey("workflow_runs.run_id"), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_completion_effects_status", "completion_effects", ["status"])
    # Transactions created before this migration may have completed cadence and
    # forecasting effects in a separate legacy transaction, then crashed before
    # writing their completion audit.  That state is indistinguishable from an
    # unfinished legacy effect.  Replaying it would be worse than omitting a
    # historical repair because it can apply EWMA twice.  Preserve legacy rows
    # as completed and create only *new* completion effects as pending in
    # ``complete_checkout_atomically``.
    op.execute(
        "INSERT INTO completion_effects "
        "(run_id, status, attempts, created_at, updated_at) "
        "SELECT run_id, 'completed', 0, completed_at, completed_at FROM transactions"
    )


def downgrade() -> None:
    op.drop_index("ix_completion_effects_status", table_name="completion_effects")
    op.drop_table("completion_effects")
