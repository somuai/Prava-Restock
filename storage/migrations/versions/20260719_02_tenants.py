"""Add tenant, membership, consent, invitation, and approval-policy support."""

from alembic import op
import sqlalchemy as sa


revision = "20260719_02"
down_revision = "20260719_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("membership_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),
    )
    op.create_table(
        "invitations",
        sa.Column("invitation_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by_user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "consents",
        sa.Column("consent_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "kind", name="uq_user_consent"),
    )
    op.create_table(
        "approval_policies",
        sa.Column("policy_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("max_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "approval_decisions",
        sa.Column("decision_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.tenant_id"), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "user_id", name="uq_workflow_approver"),
    )
    for table in (
        "tracked_items",
        "workflow_runs",
        "notifications",
        "notification_actions",
        "transactions",
        "audit_entries",
    ):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("tenant_id", sa.String(36), nullable=True))
            batch.create_index(f"ix_{table}_tenant_id", ["tenant_id"])
            batch.create_foreign_key(f"fk_{table}_tenant", "tenants", ["tenant_id"], ["tenant_id"])


def downgrade() -> None:
    for table in (
        "audit_entries",
        "transactions",
        "notification_actions",
        "notifications",
        "workflow_runs",
        "tracked_items",
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_tenant", type_="foreignkey")
            batch.drop_index(f"ix_{table}_tenant_id")
            batch.drop_column("tenant_id")
    op.drop_table("approval_decisions")
    op.drop_table("approval_policies")
    op.drop_table("consents")
    op.drop_table("invitations")
    op.drop_table("memberships")
    op.drop_table("tenants")
