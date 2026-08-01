"""Allow notification-only workflows without payment proposal fields.

Revision ID: 20260801_10
Revises: 20260730_09
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_10"
down_revision = "20260730_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch:
        batch.alter_column(
            "proposed_amount",
            existing_type=sa.Numeric(18, 2),
            nullable=True,
        )
        batch.alter_column(
            "merchant",
            existing_type=sa.String(80),
            nullable=True,
        )
        batch.create_check_constraint(
            "ck_workflow_payment_proposal_shape",
            "(proposed_action = 'flag_for_manual_renewal' "
            "AND proposed_amount IS NULL AND merchant IS NULL) OR "
            "((proposed_action IS NULL OR proposed_action <> 'flag_for_manual_renewal') "
            "AND proposed_amount IS NOT NULL AND merchant IS NOT NULL)",
        )


def downgrade() -> None:
    connection = op.get_bind()
    null_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM workflow_runs "
            "WHERE proposed_amount IS NULL OR merchant IS NULL"
        )
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            "cannot downgrade while notification-only workflows are present"
        )
    with op.batch_alter_table("workflow_runs") as batch:
        batch.drop_constraint(
            "ck_workflow_payment_proposal_shape",
            type_="check",
        )
        batch.alter_column(
            "merchant",
            existing_type=sa.String(80),
            nullable=False,
        )
        batch.alter_column(
            "proposed_amount",
            existing_type=sa.Numeric(18, 2),
            nullable=False,
        )
