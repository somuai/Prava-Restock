"""Transactional repository for workflow state and sanitized domain audit."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from payments.models import TrackedItem, User
from storage.database import Database
from storage.schema import (
    AuditRow,
    NotificationActionRow,
    NotificationRow,
    TrackedItemRow,
    TransactionRow,
    UserRow,
    WorkflowRunRow,
    SchedulerLeaseRow,
)


TERMINAL_STATES = {"completed", "failed", "skipped", "rejected", "expired"}
FORBIDDEN_AUDIT_KEYS = {
    "card_number",
    "credential_reference",
    "cvv",
    "dynamic_cvv",
    "token",
    "approval_url",
    "iframe_url",
    "payment_link",
}


def _assert_sanitized(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in FORBIDDEN_AUDIT_KEYS:
                raise ValueError(f"audit payload contains forbidden field: {key}")
            _assert_sanitized(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_sanitized(nested)


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
    }


class RestockRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_schema(self) -> None:
        self.database.create_schema()

    def upsert_user(self, user: User) -> None:
        with self.database.session() as session:
            row = session.get(UserRow, str(user.user_id)) or UserRow(
                user_id=str(user.user_id),
                display_name=user.display_name,
                prava_account_ref=user.prava_account_ref,
                monthly_cap=user.monthly_cap,
                per_item_cap=user.per_item_cap,
                per_transaction_cap=user.per_transaction_cap,
                created_at=user.created_at,
            )
            row.display_name = user.display_name
            row.monthly_cap = user.monthly_cap
            row.per_item_cap = user.per_item_cap
            row.per_transaction_cap = user.per_transaction_cap
            session.add(row)

    def upsert_item(self, item: TrackedItem) -> None:
        with self.database.session() as session:
            row = session.get(TrackedItemRow, str(item.item_id)) or TrackedItemRow(
                item_id=str(item.item_id),
                user_id=str(item.user_id),
                payload={},
            )
            row.user_id = str(item.user_id)
            row.payload = item.model_dump(mode="json")
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.get(UserRow, user_id)
            return _row_dict(row) if row else None

    def get_item(self, item_id: str) -> TrackedItem:
        with self.database.session() as session:
            row = session.get(TrackedItemRow, item_id)
            if row is None:
                raise KeyError(f"unknown item_id: {item_id}")
            return TrackedItem.model_validate(row.payload)

    def list_items(self, user_id: str) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(TrackedItemRow).where(TrackedItemRow.user_id == user_id)
            ).all()
            return [dict(row.payload) for row in rows]

    def create_workflow(
        self,
        *,
        user_id: str,
        item_id: str,
        trigger_reason: str,
        proposed_amount: Decimal,
        currency: str,
        merchant: str,
        proposed_action: str | None,
        quote: dict | None,
        modes: dict,
        idempotency_key: str,
    ) -> dict[str, Any]:
        row = WorkflowRunRow(
            user_id=user_id,
            item_id=item_id,
            state="triggered",
            active_item_key=item_id,
            trigger_reason=trigger_reason,
            proposed_amount=proposed_amount,
            currency=currency,
            merchant=merchant,
            proposed_action=proposed_action,
            quote=quote,
            idempotency_key=idempotency_key,
            modes=modes,
        )
        try:
            with self.database.session() as session:
                session.add(row)
                session.flush()
                result = _row_dict(row)
        except IntegrityError as exc:
            raise ValueError("an active workflow already exists for this item") from exc
        return result

    def get_workflow(self, run_id: str) -> dict[str, Any]:
        with self.database.session() as session:
            row = session.get(WorkflowRunRow, run_id)
            if row is None:
                raise KeyError(f"unknown run_id: {run_id}")
            return _row_dict(row)

    def list_workflows(self, user_id: str) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(WorkflowRunRow)
                .where(WorkflowRunRow.user_id == user_id)
                .order_by(WorkflowRunRow.created_at.desc())
            ).all()
            return [_row_dict(row) for row in rows]

    def transition(
        self,
        run_id: str,
        *,
        expected: set[str],
        state: str,
        **changes: Any,
    ) -> dict[str, Any]:
        with self.database.session() as session:
            row = session.get(WorkflowRunRow, run_id)
            if row is None:
                raise KeyError(f"unknown run_id: {run_id}")
            if row.state not in expected:
                raise ValueError(
                    f"workflow {run_id} is {row.state}; expected one of {sorted(expected)}"
                )
            row.state = state
            row.active_item_key = None if state in TERMINAL_STATES else row.item_id
            for key, value in changes.items():
                if not hasattr(row, key):
                    raise ValueError(f"unsupported workflow field: {key}")
                setattr(row, key, value)
            row.version += 1
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return _row_dict(row)

    def create_notification(
        self,
        *,
        run_id: str,
        user_id: str,
        message: str,
        actions: list[str],
    ) -> dict[str, Any]:
        row = NotificationRow(
            run_id=run_id,
            user_id=user_id,
            message=message,
            actions=actions,
        )
        with self.database.session() as session:
            session.add(row)
            session.flush()
            return _row_dict(row)

    def pending_notifications(self, user_id: str) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(NotificationRow).where(
                    NotificationRow.user_id == user_id,
                    NotificationRow.status == "pending",
                )
            ).all()
            return [_row_dict(row) for row in rows]

    def record_action(
        self,
        *,
        run_id: str,
        user_id: str,
        action: str,
        adjusted_amount: Decimal | None = None,
    ) -> None:
        with self.database.session() as session:
            session.add(
                NotificationActionRow(
                    run_id=run_id,
                    user_id=user_id,
                    action=action,
                    adjusted_amount=adjusted_amount,
                )
            )
            notification = session.scalar(
                select(NotificationRow).where(NotificationRow.run_id == run_id)
            )
            if notification:
                notification.status = action
                notification.updated_at = datetime.now(timezone.utc)

    def create_transaction(
        self,
        *,
        run_id: str,
        item_id: str,
        mandate_ref: str,
        merchant_order_id: str,
        amount: Decimal,
        currency: str,
        execution_mode: str,
    ) -> dict[str, Any]:
        row = TransactionRow(
            run_id=run_id,
            item_id=item_id,
            mandate_ref=mandate_ref,
            merchant_order_id=merchant_order_id,
            amount=amount,
            currency=currency,
            status="completed",
            execution_mode=execution_mode,
        )
        with self.database.session() as session:
            session.add(row)
            session.flush()
            return _row_dict(row)

    def transaction_for_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.scalar(
                select(TransactionRow).where(TransactionRow.run_id == run_id)
            )
            return _row_dict(row) if row else None

    def monthly_spend(self, user_id: str) -> Decimal:
        now = datetime.now(timezone.utc)
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        with self.database.session() as session:
            value = session.scalar(
                select(func.coalesce(func.sum(TransactionRow.amount), 0))
                .join(WorkflowRunRow, WorkflowRunRow.run_id == TransactionRow.run_id)
                .where(
                    WorkflowRunRow.user_id == user_id,
                    TransactionRow.status == "completed",
                    TransactionRow.completed_at >= month_start,
                )
            )
            return Decimal(str(value or 0))

    def acquire_lease(
        self,
        *,
        lease_name: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            row = session.get(SchedulerLeaseRow, lease_name)
            if row is not None:
                current_expiry = row.expires_at
                if current_expiry.tzinfo is None:
                    current_expiry = current_expiry.replace(tzinfo=timezone.utc)
                if current_expiry > now and row.owner_id != owner_id:
                    return False
            if row is None:
                row = SchedulerLeaseRow(
                    lease_name=lease_name,
                    owner_id=owner_id,
                    expires_at=expires_at,
                )
            else:
                row.owner_id = owner_id
                row.expires_at = expires_at
            session.add(row)
            return True

    def audit(
        self,
        *,
        user_id: str,
        event_type: str,
        payload: dict,
        modes: dict,
        run_id: str | None = None,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        _assert_sanitized(payload)
        row = AuditRow(
            run_id=run_id,
            user_id=user_id,
            item_id=item_id,
            event_type=event_type,
            payload=payload,
            modes=modes,
        )
        with self.database.session() as session:
            session.add(row)
            session.flush()
            return _row_dict(row)

    def list_audit(self, user_id: str) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(AuditRow)
                .where(AuditRow.user_id == user_id)
                .order_by(AuditRow.created_at.desc())
            ).all()
            return [_row_dict(row) for row in rows]
