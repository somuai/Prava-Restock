"""Version-one durable schema. Payment secrets are intentionally absent."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
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


class TrackedItemRow(Base):
    __tablename__ = "tracked_items"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowRunRow(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (UniqueConstraint("active_item_key", name="uq_active_item_workflow"),)

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("tracked_items.item_id"), index=True)
    state: Mapped[str] = mapped_column(String(40), index=True)
    active_item_key: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trigger_reason: Mapped[str] = mapped_column(String(80))
    proposed_amount: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    merchant: Mapped[str] = mapped_column(String(80))
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
    action: Mapped[str] = mapped_column(String(40))
    adjusted_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransactionRow(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.run_id"), unique=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("tracked_items.item_id"), index=True)
    mandate_ref: Mapped[str] = mapped_column(String(255))
    merchant_order_id: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(30))
    execution_mode: Mapped[str] = mapped_column(String(30))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditRow(Base):
    __tablename__ = "audit_entries"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
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

