"""Version-one durable schema. Payment secrets are intentionally absent."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    prava_account_ref: Mapped[str] = mapped_column(String(255))
    monthly_cap: Mapped[float] = mapped_column(Numeric(18, 2))
    per_item_cap: Mapped[float] = mapped_column(Numeric(18, 2))
    per_transaction_cap: Mapped[float] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthIdentityRow(Base):
    """External login identity; email is metadata, never an account join key."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_auth_identity_subject"),
        UniqueConstraint("user_id", "provider", name="uq_user_auth_provider"),
    )

    identity_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class WaitlistLeadRow(Base):
    """Public pilot interest, intentionally separate from users and auth."""

    __tablename__ = "waitlist_leads"

    lead_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    email_normalized: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    track_interest: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    first_use_category: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    preferred_channel: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="joined", nullable=False, index=True
    )
    pilot_email_consent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    research_opt_in: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    privacy_notice_version: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    landing_variant: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    entry_demo_track: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referrer_host: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TenantRow(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MembershipRow(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),)

    membership_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvitationRow(Base):
    __tablename__ = "invitations"

    invitation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsentRow(Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "kind", name="uq_user_consent"),)

    consent_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApprovalPolicyRow(Base):
    __tablename__ = "approval_policies"

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    scope: Mapped[str] = mapped_column(String(30), default="tenant")
    max_amount: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    required_approvals: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApprovalDecisionRow(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (UniqueConstraint("run_id", "user_id", name="uq_workflow_approver"),)

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    decision: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrackedItemRow(Base):
    __tablename__ = "tracked_items"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowRunRow(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("active_item_key", name="uq_active_item_workflow"),
        CheckConstraint(
            "(proposed_action = 'flag_for_manual_renewal' "
            "AND proposed_amount IS NULL AND merchant IS NULL) OR "
            "((proposed_action IS NULL OR proposed_action <> 'flag_for_manual_renewal') "
            "AND proposed_amount IS NOT NULL AND merchant IS NOT NULL)",
            name="ck_workflow_payment_proposal_shape",
        ),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("tracked_items.item_id"), index=True)
    state: Mapped[str] = mapped_column(String(40), index=True)
    active_item_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trigger_reason: Mapped[str] = mapped_column(String(80))
    proposed_amount: Mapped[float | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    merchant: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proposed_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quote: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prava_intent_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mandate_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    modes: Mapped[dict] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationRow(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.run_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    actions: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationActionRow(Base):
    __tablename__ = "notification_actions"

    action_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.run_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40))
    adjusted_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SlackDeliveryRow(Base):
    """Durable, one-row-per-notification Slack delivery outbox."""

    __tablename__ = "slack_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    notification_id: Mapped[str] = mapped_column(
        ForeignKey("notifications.notification_id"), unique=True, index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.run_id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    slack_message_ts: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MerchantCheckoutAttemptRow(Base):
    """Non-secret durable state around one mutating merchant checkout."""

    __tablename__ = "merchant_checkout_attempts"

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    merchant: Mapped[str] = mapped_column(String(80), index=True)
    merchant_sku_id: Mapped[str] = mapped_column(String(255))
    expected_amount: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    state: Mapped[str] = mapped_column(String(40), index=True)
    merchant_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merchant_order_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prava_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prava_txn_ref_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_exposed: Mapped[bool] = mapped_column(Boolean, default=False)
    credential_used: Mapped[bool] = mapped_column(Boolean, default=False)
    report_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    report_state: Mapped[str] = mapped_column(String(30), default="not_required", index=True)
    report_attempts: Mapped[int] = mapped_column(default=0)
    prava_reported: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthLoginThrottleRow(Base):
    """Durable, non-identifying login-attempt window shared by API replicas."""

    __tablename__ = "auth_login_throttles"

    source_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionRow(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.run_id"), unique=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("tracked_items.item_id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    mandate_ref: Mapped[str] = mapped_column(String(255))
    merchant_order_id: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(30))
    execution_mode: Mapped[str] = mapped_column(String(30))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompletionEffectsRow(Base):
    """Exactly-once durable work created with a completed checkout."""

    __tablename__ = "completion_effects"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_runs.run_id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditRow(Base):
    __tablename__ = "audit_entries"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    modes: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SchedulerLeaseRow(Base):
    __tablename__ = "scheduler_leases"

    lease_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ForecastObservationRow(Base):
    __tablename__ = "forecast_observations"

    observation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("tracked_items.item_id"), index=True)
    predicted_depletion_date: Mapped[str] = mapped_column(String(10))
    actual_reorder_date: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    household_size: Mapped[int | None] = mapped_column(nullable=True)
    trigger_cause: Mapped[str] = mapped_column(String(80))
    notification_action: Mapped[str] = mapped_column(String(40))
    forecast_error_days: Mapped[float] = mapped_column(Numeric(18, 3))
    model_version: Mapped[str] = mapped_column(String(40), default="ewma-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
