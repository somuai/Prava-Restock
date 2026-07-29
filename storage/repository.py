"""Transactional repository for workflow state and sanitized domain audit."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import secrets
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError

from payments.models import TrackedItem, User
from storage.database import Database
from storage.schema import (
    AuditRow,
    AuthLoginThrottleRow,
    ApprovalDecisionRow,
    ApprovalPolicyRow,
    ConsentRow,
    CompletionEffectsRow,
    ForecastObservationRow,
    InvitationRow,
    MembershipRow,
    MerchantCheckoutAttemptRow,
    NotificationActionRow,
    NotificationRow,
    TrackedItemRow,
    TransactionRow,
    UserRow,
    WorkflowRunRow,
    SchedulerLeaseRow,
    SlackDeliveryRow,
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

    def list_schedulable_items(self) -> list[tuple[User, TrackedItem]]:
        """Return active persisted items with their owners for the leased worker."""

        with self.database.session() as session:
            rows = session.execute(
                select(TrackedItemRow, UserRow).join(
                    UserRow, UserRow.user_id == TrackedItemRow.user_id
                )
            ).all()
            candidates: list[tuple[User, TrackedItem]] = []
            for item_row, user_row in rows:
                item = TrackedItem.model_validate(item_row.payload)
                if item.status.value != "active":
                    continue
                user = User.model_validate(_row_dict(user_row))
                candidates.append((user, item))
            return candidates

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
            notification_ids = select(NotificationRow.notification_id).where(
                NotificationRow.user_id == user_id
            )
            session.execute(delete(SlackDeliveryRow).where(
                SlackDeliveryRow.notification_id.in_(notification_ids)
            ))
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
        try:
            with self.database.session() as session:
                item_row = session.get(TrackedItemRow, item_id)
                tenant_id = item_row.tenant_id if item_row else None
                pending_effect = session.scalar(
                    select(CompletionEffectsRow.run_id)
                    .join(
                        WorkflowRunRow,
                        WorkflowRunRow.run_id == CompletionEffectsRow.run_id,
                    )
                    .where(
                        WorkflowRunRow.item_id == item_id,
                        CompletionEffectsRow.status == "pending",
                    )
                    .limit(1)
                )
                if pending_effect is not None:
                    raise ValueError(
                        "completion effects are pending for this item; retry after recovery"
                    )
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

    def workflow_for_checkout_key(self, idempotency_key: str) -> dict[str, Any]:
        with self.database.session() as session:
            row = session.scalar(
                select(WorkflowRunRow).where(
                    WorkflowRunRow.idempotency_key == idempotency_key
                )
            )
            if row is None:
                raise KeyError(f"unknown checkout idempotency key: {idempotency_key}")
            return _row_dict(row)

    def list_workflows(self, user_id: str) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(WorkflowRunRow)
                .where(WorkflowRunRow.user_id == user_id)
                .order_by(WorkflowRunRow.created_at.desc())
            ).all()
            return [_row_dict(row) for row in rows]

    def latest_workflow_for_item(self, item_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.scalar(
                select(WorkflowRunRow)
                .where(WorkflowRunRow.item_id == item_id)
                .order_by(WorkflowRunRow.created_at.desc())
                .limit(1)
            )
            return _row_dict(row) if row else None

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
        with self.database.session() as session:
            run = session.get(WorkflowRunRow, run_id)
            if run is None:
                raise KeyError(f"unknown run_id: {run_id}")
            item = session.get(TrackedItemRow, run.item_id)
            if item is None:
                raise KeyError(f"unknown item_id: {run.item_id}")
            row = NotificationRow(
                run_id=run_id,
                user_id=user_id,
                tenant_id=run.tenant_id,
                message=message,
                actions=actions,
            )
            session.add(row)
            session.flush()
            if item.payload.get("track") == "teams":
                session.add(SlackDeliveryRow(
                    notification_id=row.notification_id,
                    run_id=run_id,
                ))
                session.flush()
            return _row_dict(row)

    def slack_delivery_for_notification(self, notification_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.scalar(select(SlackDeliveryRow).where(
                SlackDeliveryRow.notification_id == notification_id
            ))
            return _row_dict(row) if row else None

    def reserve_merchant_checkout_attempt(
        self,
        *,
        idempotency_key: str,
        merchant: str,
        merchant_sku_id: str,
        expected_amount: Decimal,
        currency: str,
        prava_session_id: str,
        prava_txn_ref_id: str,
    ) -> tuple[dict[str, Any], bool]:
        """Create the durable idempotency record before any merchant mutation."""

        def validate(row: MerchantCheckoutAttemptRow) -> dict[str, Any]:
            immutable = (
                row.merchant == merchant
                and row.merchant_sku_id == merchant_sku_id
                and Decimal(str(row.expected_amount)) == Decimal(str(expected_amount))
                and row.currency == currency
                and row.prava_session_id == prava_session_id
                and row.prava_txn_ref_id == prava_txn_ref_id
            )
            if not immutable:
                raise ValueError("idempotency key is already bound to another checkout")
            return _row_dict(row)

        with self.database.session() as session:
            existing = session.get(MerchantCheckoutAttemptRow, idempotency_key)
            if existing is not None:
                return validate(existing), False

        row = MerchantCheckoutAttemptRow(
            idempotency_key=idempotency_key,
            merchant=merchant,
            merchant_sku_id=merchant_sku_id,
            expected_amount=expected_amount,
            currency=currency,
            state="reserved",
            prava_session_id=prava_session_id,
            prava_txn_ref_id=prava_txn_ref_id,
        )
        try:
            with self.database.session() as session:
                session.add(row)
                session.flush()
                return validate(row), True
        except IntegrityError:
            # A concurrent worker won the unique insert. Re-read and verify that
            # the key is bound to the exact same immutable checkout request.
            with self.database.session() as session:
                existing = session.get(MerchantCheckoutAttemptRow, idempotency_key)
                if existing is None:
                    raise
                return validate(existing), False

    def get_merchant_checkout_attempt(self, idempotency_key: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.get(MerchantCheckoutAttemptRow, idempotency_key)
            return _row_dict(row) if row else None

    def consume_login_attempt(
        self,
        *,
        source_hash: str,
        limit: int,
        window_seconds: int = 60,
        now: datetime | None = None,
    ) -> bool:
        """Atomically consume one durable login-attempt slot.

        Production Postgres replicas serialize the same source with a
        transaction-scoped advisory lock. SQLite supports deterministic local
        and restart tests but is never accepted for production authentication.
        """
        if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
            raise ValueError("source_hash must be a lowercase SHA-256 hex digest")
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("login-attempt limit and window must be positive")
        checked_at = now or datetime.now(timezone.utc)
        with self.database.session() as session:
            if self.database.engine.dialect.name == "postgresql":
                lock_id = int(source_hash[:16], 16)
                if lock_id >= 1 << 63:
                    lock_id -= 1 << 64
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": lock_id},
                )
            row = session.get(AuthLoginThrottleRow, source_hash)
            if row is None:
                session.add(AuthLoginThrottleRow(
                    source_hash=source_hash,
                    window_started_at=checked_at,
                    attempts=1,
                    updated_at=checked_at,
                ))
                return True
            window_started_at = row.window_started_at
            if window_started_at.tzinfo is None:
                window_started_at = window_started_at.replace(tzinfo=timezone.utc)
            if checked_at - window_started_at >= timedelta(seconds=window_seconds):
                row.window_started_at = checked_at
                row.attempts = 1
                row.updated_at = checked_at
                return True
            if row.attempts >= limit:
                return False
            row.attempts += 1
            row.updated_at = checked_at
            return True

    def update_merchant_checkout_attempt(
        self,
        idempotency_key: str,
        *,
        expected_states: set[str] | None = None,
        expected_report_states: set[str] | None = None,
        **changes: Any,
    ) -> dict[str, Any]:
        allowed = {
            "state",
            "merchant_order_id",
            "merchant_order_code",
            "credential_exposed",
            "credential_used",
            "report_status",
            "report_state",
            "report_attempts",
            "prava_reported",
            "last_error",
        }
        unsupported = set(changes).difference(allowed)
        if unsupported:
            raise ValueError(f"unsupported checkout-attempt fields: {sorted(unsupported)}")
        values = {**changes, "updated_at": datetime.now(timezone.utc)}
        with self.database.session() as session:
            statement = update(MerchantCheckoutAttemptRow).where(
                MerchantCheckoutAttemptRow.idempotency_key == idempotency_key
            )
            if expected_states is not None:
                statement = statement.where(
                    MerchantCheckoutAttemptRow.state.in_(expected_states)
                )
            if expected_report_states is not None:
                statement = statement.where(
                    MerchantCheckoutAttemptRow.report_state.in_(expected_report_states)
                )
            result = session.execute(statement.values(**values))
            if result.rowcount != 1:
                row = session.get(MerchantCheckoutAttemptRow, idempotency_key)
                if row is None:
                    raise KeyError(
                        f"unknown checkout idempotency key: {idempotency_key}"
                    )
                raise ValueError("checkout-attempt compare-and-swap failed")
            row = session.get(MerchantCheckoutAttemptRow, idempotency_key)
            assert row is not None
            session.refresh(row)
            return _row_dict(row)

    def claim_merchant_checkout_report(self, idempotency_key: str) -> dict[str, Any] | None:
        """Atomically claim one pending Prava status report for delivery."""

        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            result = session.execute(
                update(MerchantCheckoutAttemptRow)
                .where(
                    MerchantCheckoutAttemptRow.idempotency_key == idempotency_key,
                    MerchantCheckoutAttemptRow.report_state == "pending",
                    MerchantCheckoutAttemptRow.report_status.in_(("APPROVED", "DECLINED")),
                )
                .values(
                    report_state="sending",
                    report_attempts=MerchantCheckoutAttemptRow.report_attempts + 1,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                return None
            row = session.get(MerchantCheckoutAttemptRow, idempotency_key)
            assert row is not None
            session.refresh(row)
            return _row_dict(row)

    def claim_slack_delivery(
        self,
        *,
        owner_id: str,
        lease_seconds: int = 30,
    ) -> dict[str, Any] | None:
        """Claim one pending delivery; ambiguous attempts are never auto-retried."""

        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            query = (
                select(SlackDeliveryRow)
                .where(SlackDeliveryRow.status == "pending")
                .order_by(SlackDeliveryRow.created_at)
                .limit(1)
            )
            if self.database.engine.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
            row = session.scalar(query)
            if row is None:
                return None
            row.status = "sending"
            row.attempts += 1
            row.lease_owner = owner_id
            row.lease_expires_at = now + timedelta(seconds=max(10, lease_seconds))
            row.updated_at = now
            notification = session.get(NotificationRow, row.notification_id)
            if notification is None:
                row.status = "failed_ambiguous"
                row.last_error = "notification_missing"
                return None
            session.flush()
            return {**_row_dict(row), "notification": _row_dict(notification)}

    def complete_slack_delivery(
        self,
        *,
        delivery_id: str,
        owner_id: str,
        slack_message_ts: str,
    ) -> None:
        with self.database.session() as session:
            row = session.get(SlackDeliveryRow, delivery_id)
            if row is None or row.status != "sending" or row.lease_owner != owner_id:
                raise ValueError("Slack delivery is not owned by this dispatcher")
            row.status = "sent"
            row.slack_message_ts = slack_message_ts
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = datetime.now(timezone.utc)

    def fail_slack_delivery(
        self,
        *,
        delivery_id: str,
        owner_id: str,
        error_code: str,
    ) -> None:
        with self.database.session() as session:
            row = session.get(SlackDeliveryRow, delivery_id)
            if row is None or row.status != "sending" or row.lease_owner != owner_id:
                raise ValueError("Slack delivery is not owned by this dispatcher")
            row.status = "failed_ambiguous"
            row.last_error = error_code[:120]
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = datetime.now(timezone.utc)

    def pending_notifications(self, user_id: str) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(NotificationRow, WorkflowRunRow, TrackedItemRow)
                .join(WorkflowRunRow, WorkflowRunRow.run_id == NotificationRow.run_id)
                .join(TrackedItemRow, TrackedItemRow.item_id == WorkflowRunRow.item_id)
                .where(
                    NotificationRow.user_id == user_id,
                    NotificationRow.status == "pending",
                )
            ).all()
            result = []
            for notification, run, item in rows:
                value = _row_dict(notification)
                value["item_id"] = run.item_id
                value["track"] = item.payload.get("track")
                result.append(value)
            return result

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
        disclosure_reason: str | None = None,
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

    def complete_checkout_atomically(
        self,
        *,
        run_id: str,
        expected_state: str,
        item_id: str,
        mandate_ref: str,
        merchant_order_id: str,
        amount: Decimal,
        currency: str,
        execution_mode: str,
        disclosure_reason: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Create-or-verify one transaction and terminalize its run atomically."""

        immutable = {
            "item_id": item_id,
            "mandate_ref": mandate_ref,
            "merchant_order_id": merchant_order_id,
            "amount": Decimal(str(amount)).quantize(Decimal("0.01")),
            "currency": currency,
            "execution_mode": execution_mode,
        }
        with self.database.session() as session:
            if self.database.engine.dialect.name == "sqlite":
                # SQLite has no row-level FOR UPDATE; serialize this narrow local
                # test/dev boundary so the unique transaction check remains CAS-like.
                session.execute(text("BEGIN IMMEDIATE"))
            statement = select(WorkflowRunRow).where(WorkflowRunRow.run_id == run_id)
            if self.database.engine.dialect.name == "postgresql":
                statement = statement.with_for_update()
            run = session.scalar(statement)
            if run is None:
                raise KeyError(f"unknown run_id: {run_id}")
            locked_amount = Decimal(str(run.proposed_amount)).quantize(Decimal("0.01"))
            if immutable["amount"] != locked_amount or currency != run.currency:
                raise ValueError(
                    "merchant outcome amount/currency does not match the locked workflow"
                )
            transaction = session.scalar(
                select(TransactionRow).where(TransactionRow.run_id == run_id)
            )
            if transaction is not None:
                matches = (
                    transaction.item_id == immutable["item_id"]
                    and transaction.mandate_ref == immutable["mandate_ref"]
                    and transaction.merchant_order_id == immutable["merchant_order_id"]
                    and Decimal(str(transaction.amount)).quantize(Decimal("0.01"))
                    == immutable["amount"]
                    and transaction.currency == immutable["currency"]
                    and transaction.execution_mode == immutable["execution_mode"]
                )
                if not matches or run.state != "completed":
                    raise ValueError(
                        "existing checkout transaction does not match terminal workflow"
                    )
                if session.get(CompletionEffectsRow, run_id) is None:
                    session.add(CompletionEffectsRow(run_id=run_id, status="pending"))
                    session.flush()
                return _row_dict(run), _row_dict(transaction)
            if run.state != expected_state:
                raise ValueError(
                    f"workflow {run_id} is {run.state}; expected {expected_state}"
                )
            transaction = TransactionRow(
                run_id=run_id,
                item_id=item_id,
                tenant_id=run.tenant_id,
                mandate_ref=mandate_ref,
                merchant_order_id=merchant_order_id,
                amount=immutable["amount"],
                currency=currency,
                status="completed",
                execution_mode=execution_mode,
            )
            session.add(transaction)
            run.state = "completed"
            run.active_item_key = None
            run.error_code = None
            run_modes = dict(run.modes)
            run_modes["home_payment"] = execution_mode
            if disclosure_reason:
                run_modes["home_payment_reason"] = disclosure_reason
            run.modes = run_modes
            run.version += 1
            run.updated_at = datetime.now(timezone.utc)
            session.add(CompletionEffectsRow(run_id=run_id, status="pending"))
            session.flush()
            return _row_dict(run), _row_dict(transaction)

    def transaction_for_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.scalar(
                select(TransactionRow).where(TransactionRow.run_id == run_id)
            )
            return _row_dict(row) if row else None

    def completion_effects_for_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            row = session.get(CompletionEffectsRow, run_id)
            return _row_dict(row) if row else None

    def pending_completion_run_ids(self, *, limit: int = 100) -> list[str]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self.database.session() as session:
            rows = session.scalars(
                select(CompletionEffectsRow.run_id)
                .where(CompletionEffectsRow.status == "pending")
                .order_by(CompletionEffectsRow.created_at)
                .limit(limit)
            ).all()
            return list(rows)

    def apply_completion_effects(
        self,
        *,
        run_id: str,
        item_payload: dict[str, Any] | None,
        forecast: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Apply the required completion audit and optional Home learning once."""

        with self.database.session() as session:
            if self.database.engine.dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            statement = select(CompletionEffectsRow).where(
                CompletionEffectsRow.run_id == run_id
            )
            if self.database.engine.dialect.name == "postgresql":
                statement = statement.with_for_update()
            work = session.scalar(statement)
            if work is None:
                raise KeyError(f"completion effects are missing for run: {run_id}")
            if work.status == "completed":
                return _row_dict(work)
            run = session.get(WorkflowRunRow, run_id)
            transaction = session.scalar(
                select(TransactionRow).where(TransactionRow.run_id == run_id)
            )
            if run is None or run.state != "completed" or transaction is None:
                raise ValueError("completion effects require a terminal run and transaction")

            audit_payload = {
                "transaction_id": transaction.transaction_id,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
            }
            _assert_sanitized(audit_payload)
            existing_audit = session.scalar(
                select(AuditRow).where(
                    AuditRow.run_id == run_id,
                    AuditRow.event_type == "transaction_completed",
                )
            )
            if existing_audit is None:
                session.add(
                    AuditRow(
                        run_id=run_id,
                        user_id=run.user_id,
                        tenant_id=run.tenant_id,
                        item_id=run.item_id,
                        event_type="transaction_completed",
                        payload=audit_payload,
                        modes=run.modes,
                    )
                )
            # Before this outbox existed, the completion audit was written only
            # after cadence/forecast updates. Its presence is therefore the
            # compatibility marker that all legacy effects already ran.
            apply_domain_effects = existing_audit is None
            if apply_domain_effects and item_payload is not None:
                item = session.get(TrackedItemRow, run.item_id)
                if item is None:
                    raise KeyError(f"unknown item_id: {run.item_id}")
                item.payload = item_payload
                item.updated_at = datetime.now(timezone.utc)
            if apply_domain_effects and forecast is not None:
                consent = session.scalar(
                    select(ConsentRow).where(
                        ConsentRow.tenant_id == forecast["tenant_id"],
                        ConsentRow.user_id == forecast["user_id"],
                        ConsentRow.kind == "forecasting",
                        ConsentRow.granted.is_(True),
                    )
                )
                if consent is not None:
                    session.add(ForecastObservationRow(**forecast))
            work.status = "completed"
            work.attempts += 1
            work.last_error = None
            work.updated_at = datetime.now(timezone.utc)
            session.flush()
            return _row_dict(work)

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

    def active_workflow_commitments(
        self, user_id: str, *, exclude_run_id: str | None = None
    ) -> Decimal:
        """Return amounts reserved by nonterminal workflows for cap decisions."""

        with self.database.session() as session:
            query = select(
                func.coalesce(func.sum(WorkflowRunRow.proposed_amount), 0)
            ).where(
                WorkflowRunRow.user_id == user_id,
                WorkflowRunRow.active_item_key.is_not(None),
            )
            if exclude_run_id is not None:
                query = query.where(WorkflowRunRow.run_id != exclude_run_id)
            value = session.scalar(query)
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
            claimed = session.execute(
                update(SchedulerLeaseRow)
                .where(
                    SchedulerLeaseRow.lease_name == lease_name,
                    (SchedulerLeaseRow.expires_at <= now)
                    | (SchedulerLeaseRow.owner_id == owner_id),
                )
                .values(owner_id=owner_id, expires_at=expires_at)
            )
            if claimed.rowcount == 1:
                return True
        try:
            with self.database.session() as session:
                session.add(SchedulerLeaseRow(
                    lease_name=lease_name,
                    owner_id=owner_id,
                    expires_at=expires_at,
                ))
                session.flush()
                return True
        except IntegrityError:
            return False

    def release_lease(self, *, lease_name: str, owner_id: str) -> bool:
        """Release only the caller's lease; never delete another owner's claim."""

        with self.database.session() as session:
            result = session.execute(
                delete(SchedulerLeaseRow).where(
                    SchedulerLeaseRow.lease_name == lease_name,
                    SchedulerLeaseRow.owner_id == owner_id,
                )
            )
            return result.rowcount == 1

    def renew_lease(
        self,
        *,
        lease_name: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        """Renew only an unexpired lease still owned by the caller.

        Refusing resurrection after expiry is the fencing boundary: once a
        later owner can acquire the name, an earlier operation cannot resume.
        """

        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            result = session.execute(
                update(SchedulerLeaseRow)
                .where(
                    SchedulerLeaseRow.lease_name == lease_name,
                    SchedulerLeaseRow.owner_id == owner_id,
                    SchedulerLeaseRow.expires_at > now,
                )
                .values(expires_at=expires_at)
            )
            return result.rowcount == 1

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
            resolved_notification_ids = select(NotificationRow.notification_id).where(
                NotificationRow.created_at < before,
                NotificationRow.status != "pending",
            )
            session.execute(delete(SlackDeliveryRow).where(
                SlackDeliveryRow.notification_id.in_(resolved_notification_ids)
            ))
            notification_result = session.execute(delete(NotificationRow).where(
                NotificationRow.created_at < before,
                NotificationRow.status != "pending",
            ))
            return {
                "audit_entries": int(audit_result.rowcount or 0),
                "notifications": int(notification_result.rowcount or 0),
            }
