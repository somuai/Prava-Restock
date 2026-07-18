"""Transactional repository for workflow state and sanitized domain audit."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from payments.models import TrackedItem, User
from storage.database import Database
from storage.schema import (
    AuditRow,
    ApprovalDecisionRow,
    ApprovalPolicyRow,
    ConsentRow,
    ForecastObservationRow,
    InvitationRow,
    MembershipRow,
    NotificationActionRow,
    NotificationRow,
    TrackedItemRow,
    TransactionRow,
    UserRow,
    WorkflowRunRow,
    SchedulerLeaseRow,
    TenantRow,
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
        self.ensure_personal_tenant(str(user.user_id))

    @staticmethod
    def personal_tenant_id(user_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"restock:personal:{user_id}"))

    def ensure_personal_tenant(self, user_id: str) -> str:
        tenant_id = self.personal_tenant_id(user_id)
        with self.database.session() as session:
            tenant = session.get(TenantRow, tenant_id)
            if tenant is None:
                user = session.get(UserRow, user_id)
                if user is None:
                    raise KeyError(f"unknown user_id: {user_id}")
                session.add(TenantRow(
                    tenant_id=tenant_id,
                    name=f"{user.display_name}'s household",
                    kind="household",
                    created_by_user_id=user_id,
                ))
                session.flush()
            membership = session.scalar(select(MembershipRow).where(
                MembershipRow.tenant_id == tenant_id,
                MembershipRow.user_id == user_id,
            ))
            if membership is None:
                session.add(MembershipRow(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role="owner",
                    status="active",
                ))
        return tenant_id

    def upsert_item(self, item: TrackedItem) -> None:
        tenant_id = str(item.tenant_id) if item.tenant_id else self.ensure_personal_tenant(str(item.user_id))
        self.require_membership(tenant_id, str(item.user_id), {"owner", "admin", "member"})
        with self.database.session() as session:
            row = session.get(TrackedItemRow, str(item.item_id)) or TrackedItemRow(
                item_id=str(item.item_id),
                user_id=str(item.user_id),
                tenant_id=tenant_id,
                payload={},
            )
            row.user_id = str(item.user_id)
            row.tenant_id = tenant_id
            payload = item.model_dump(mode="json")
            payload["tenant_id"] = tenant_id
            row.payload = payload
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

    def list_items(self, user_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(TrackedItemRow)
            if tenant_id:
                self.require_membership(tenant_id, user_id)
                query = query.where(TrackedItemRow.tenant_id == tenant_id)
            else:
                query = query.where(TrackedItemRow.user_id == user_id)
            rows = session.scalars(query).all()
            return [dict(row.payload) for row in rows]

    def create_tenant(self, *, name: str, kind: str, owner_user_id: str) -> dict[str, Any]:
        if kind not in {"household", "organization"}:
            raise ValueError("tenant kind must be household or organization")
        tenant_id = str(uuid4())
        with self.database.session() as session:
            if session.get(UserRow, owner_user_id) is None:
                raise KeyError(f"unknown user_id: {owner_user_id}")
            tenant = TenantRow(
                tenant_id=tenant_id,
                name=name,
                kind=kind,
                created_by_user_id=owner_user_id,
            )
            session.add(tenant)
            session.flush()
            session.add(MembershipRow(
                tenant_id=tenant_id,
                user_id=owner_user_id,
                role="owner",
                status="active",
            ))
            return _row_dict(tenant)

    def require_membership(
        self,
        tenant_id: str,
        user_id: str,
        roles: set[str] | None = None,
    ) -> dict[str, Any]:
        with self.database.session() as session:
            row = session.scalar(select(MembershipRow).where(
                MembershipRow.tenant_id == tenant_id,
                MembershipRow.user_id == user_id,
                MembershipRow.status == "active",
            ))
            if row is None or (roles is not None and row.role not in roles):
                raise PermissionError("user is not authorized for this tenant")
            return _row_dict(row)

    def list_tenants(self, user_id: str) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(TenantRow, MembershipRow.role)
                .join(MembershipRow, MembershipRow.tenant_id == TenantRow.tenant_id)
                .where(MembershipRow.user_id == user_id, MembershipRow.status == "active")
            ).all()
            return [{**_row_dict(tenant), "role": role} for tenant, role in rows]

    def list_members(self, tenant_id: str, actor_user_id: str) -> list[dict[str, Any]]:
        self.require_membership(tenant_id, actor_user_id)
        with self.database.session() as session:
            rows = session.scalars(select(MembershipRow).where(
                MembershipRow.tenant_id == tenant_id,
                MembershipRow.status == "active",
            )).all()
            return [_row_dict(row) for row in rows]

    def invite_member(
        self,
        *,
        tenant_id: str,
        actor_user_id: str,
        email: str,
        role: str,
        ttl_hours: int = 72,
    ) -> dict[str, Any]:
        self.require_membership(tenant_id, actor_user_id, {"owner", "admin"})
        if role not in {"admin", "approver", "member"}:
            raise ValueError("invalid invited role")
        token = secrets.token_urlsafe(32)
        row = InvitationRow(
            tenant_id=tenant_id,
            email=email.strip().lower(),
            role=role,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            invited_by_user_id=actor_user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        )
        with self.database.session() as session:
            session.add(row)
            session.flush()
            result = _row_dict(row)
        result["token"] = token
        result.pop("token_hash", None)
        return result

    def accept_invitation(self, *, token: str, user_id: str) -> dict[str, Any]:
        digest = hashlib.sha256(token.encode()).hexdigest()
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            invitation = session.scalar(select(InvitationRow).where(InvitationRow.token_hash == digest))
            if invitation is None or invitation.accepted_at is not None:
                raise ValueError("invitation is invalid or already used")
            expiry = invitation.expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= now:
                raise ValueError("invitation expired")
            if session.get(UserRow, user_id) is None:
                raise KeyError(f"unknown user_id: {user_id}")
            invitation.accepted_at = now
            membership = MembershipRow(
                tenant_id=invitation.tenant_id,
                user_id=user_id,
                role=invitation.role,
                status="active",
            )
            session.add(membership)
            session.flush()
            return _row_dict(membership)

    def set_consent(self, *, tenant_id: str, user_id: str, kind: str, granted: bool) -> dict[str, Any]:
        self.require_membership(tenant_id, user_id)
        with self.database.session() as session:
            row = session.scalar(select(ConsentRow).where(
                ConsentRow.tenant_id == tenant_id,
                ConsentRow.user_id == user_id,
                ConsentRow.kind == kind,
            ))
            if row is None:
                row = ConsentRow(tenant_id=tenant_id, user_id=user_id, kind=kind)
            row.granted = granted
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.flush()
            return _row_dict(row)

    def has_consent(self, *, tenant_id: str, user_id: str, kind: str) -> bool:
        with self.database.session() as session:
            row = session.scalar(select(ConsentRow).where(
                ConsentRow.tenant_id == tenant_id,
                ConsentRow.user_id == user_id,
                ConsentRow.kind == kind,
                ConsentRow.granted.is_(True),
            ))
            return row is not None

    def log_forecast_observation(
        self,
        *,
        tenant_id: str,
        user_id: str,
        item_id: str,
        predicted_depletion_date: str,
        actual_reorder_date: str,
        category: str,
        trigger_cause: str,
        notification_action: str,
        forecast_error_days: float,
        quantity: Decimal | None = None,
        household_size: int | None = None,
        model_version: str = "ewma-v1",
    ) -> dict[str, Any] | None:
        if not self.has_consent(tenant_id=tenant_id, user_id=user_id, kind="forecasting"):
            return None
        row = ForecastObservationRow(
            tenant_id=tenant_id,
            user_id=user_id,
            item_id=item_id,
            predicted_depletion_date=predicted_depletion_date,
            actual_reorder_date=actual_reorder_date,
            category=category,
            quantity=quantity,
            household_size=household_size,
            trigger_cause=trigger_cause,
            notification_action=notification_action,
            forecast_error_days=forecast_error_days,
            model_version=model_version,
        )
        with self.database.session() as session:
            session.add(row)
            session.flush()
            return _row_dict(row)

    def list_forecast_observations(self, *, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        self.require_membership(tenant_id, user_id)
        with self.database.session() as session:
            rows = session.scalars(select(ForecastObservationRow).where(
                ForecastObservationRow.tenant_id == tenant_id,
                ForecastObservationRow.user_id == user_id,
            )).all()
            return [_row_dict(row) for row in rows]

    def delete_forecast_observations(self, *, tenant_id: str, user_id: str) -> int:
        self.require_membership(tenant_id, user_id)
        with self.database.session() as session:
            rows = session.scalars(select(ForecastObservationRow).where(
                ForecastObservationRow.tenant_id == tenant_id,
                ForecastObservationRow.user_id == user_id,
            )).all()
            for row in rows:
                session.delete(row)
            return len(rows)

    def create_approval_policy(
        self,
        *,
        tenant_id: str,
        actor_user_id: str,
        max_amount: Decimal,
        currency: str,
        required_approvals: int,
    ) -> dict[str, Any]:
        self.require_membership(tenant_id, actor_user_id, {"owner", "admin"})
        if required_approvals < 1:
            raise ValueError("required approvals must be positive")
        row = ApprovalPolicyRow(
            tenant_id=tenant_id,
            max_amount=max_amount,
            currency=currency,
            required_approvals=required_approvals,
        )
        with self.database.session() as session:
            session.add(row)
            session.flush()
            return _row_dict(row)

    def record_approval_decision(
        self,
        *,
        tenant_id: str,
        run_id: str,
        user_id: str,
        decision: str,
        required_approvals: int = 1,
    ) -> dict[str, Any]:
        self.require_membership(tenant_id, user_id, {"owner", "admin", "approver"})
        if decision not in {"approve", "skip", "renew_as_is", "switch_plan"}:
            raise ValueError("unsupported approval decision")
        run = self.get_workflow(run_id)
        if run.get("tenant_id") != tenant_id:
            raise PermissionError("workflow belongs to a different tenant")
        try:
            with self.database.session() as session:
                session.add(ApprovalDecisionRow(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    user_id=user_id,
                    decision=decision,
                ))
                session.flush()
                decisions = session.scalars(select(ApprovalDecisionRow).where(
                    ApprovalDecisionRow.run_id == run_id,
                )).all()
        except IntegrityError as exc:
            raise ValueError("approver already decided this workflow") from exc
        # Conflict policy: an explicit skip is a veto while pending; otherwise
        # identical positive decisions must reach the configured threshold.
        if any(row.decision == "skip" for row in decisions):
            outcome = "vetoed"
        else:
            positives = [row.decision for row in decisions]
            outcome = positives[0] if len(positives) >= required_approvals and len(set(positives)) == 1 else "pending"
        return {"outcome": outcome, "decision_count": len(decisions)}

    def privacy_export(self, user_id: str) -> dict[str, Any]:
        with self.database.session() as session:
            return {
                "user": _row_dict(session.get(UserRow, user_id)) if session.get(UserRow, user_id) else None,
                "tenants": self.list_tenants(user_id),
                "items": [dict(row.payload) for row in session.scalars(select(TrackedItemRow).where(TrackedItemRow.user_id == user_id)).all()],
                "actions": [_row_dict(row) for row in session.scalars(select(NotificationActionRow).where(NotificationActionRow.user_id == user_id)).all()],
                "audit": self.list_audit(user_id),
            }

    def delete_user_data(self, user_id: str) -> None:
        """Privacy deletion removes user-authored activity and pseudonymizes retained payment proof."""
        with self.database.session() as session:
            for model in (ConsentRow, NotificationActionRow, NotificationRow, MembershipRow):
                for row in session.scalars(select(model).where(model.user_id == user_id)).all():
                    session.delete(row)
            user = session.get(UserRow, user_id)
            if user:
                user.display_name = "Deleted user"
                user.prava_account_ref = "deleted"

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
        with self.database.session() as session:
            item_row = session.get(TrackedItemRow, item_id)
            tenant_id = item_row.tenant_id if item_row else None
        row = WorkflowRunRow(
            user_id=user_id,
            tenant_id=tenant_id,
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
        run = self.get_workflow(run_id)
        row = NotificationRow(
            run_id=run_id,
            user_id=user_id,
            tenant_id=run.get("tenant_id"),
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
        run = self.get_workflow(run_id)
        with self.database.session() as session:
            session.add(
                NotificationActionRow(
                    run_id=run_id,
                    user_id=user_id,
                    tenant_id=run.get("tenant_id"),
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
        run = self.get_workflow(run_id)
        row = TransactionRow(
            run_id=run_id,
            item_id=item_id,
            tenant_id=run.get("tenant_id"),
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
        tenant_id = None
        if run_id:
            tenant_id = self.get_workflow(run_id).get("tenant_id")
        row = AuditRow(
            run_id=run_id,
            user_id=user_id,
            tenant_id=tenant_id,
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

    def enforce_retention(self, *, before: datetime) -> dict[str, int]:
        """Delete old audit and resolved notification records; payment proof is retained."""
        with self.database.session() as session:
            audit_result = session.execute(delete(AuditRow).where(AuditRow.created_at < before))
            notification_result = session.execute(delete(NotificationRow).where(
                NotificationRow.created_at < before,
                NotificationRow.status != "pending",
            ))
            return {
                "audit_entries": int(audit_result.rowcount or 0),
                "notifications": int(notification_result.rowcount or 0),
            }
