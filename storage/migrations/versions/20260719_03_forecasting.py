"""Add consent-gated forecasting observations."""

from alembic import op
import sqlalchemy as sa


revision = "20260719_03"
down_revision = "20260719_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_observations",
        sa.Column("observation_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("tracked_items.item_id"), nullable=False),
        sa.Column("predicted_depletion_date", sa.String(10), nullable=False),
        sa.Column("actual_reorder_date", sa.String(10), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=True),
        sa.Column("household_size", sa.Integer(), nullable=True),
        sa.Column("trigger_cause", sa.String(80), nullable=False),
        sa.Column("notification_action", sa.String(40), nullable=False),
        sa.Column("forecast_error_days", sa.Numeric(18, 3), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_forecast_observations_tenant_id", "forecast_observations", ["tenant_id"])
    op.create_index("ix_forecast_observations_user_id", "forecast_observations", ["user_id"])
    op.create_index("ix_forecast_observations_item_id", "forecast_observations", ["item_id"])


def downgrade() -> None:
    op.drop_table("forecast_observations")
