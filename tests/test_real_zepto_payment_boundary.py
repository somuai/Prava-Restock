from datetime import datetime, timezone
from decimal import Decimal

import pytest

from merchant import zepto_checkout
from payments import prava_client
from storage.database import Database
from storage.repository import RestockRepository
from storage.schema import MerchantCheckoutAttemptRow


class FakeZeptoClient:
    def __init__(self, *, total="412.50", statuses=None, create_error=False, history=None, payment_link="https://checkout.juspay.in/payment/short-lived"):
        self.total = total
        self.statuses = list(statuses or ["SUCCESS"])
        self.create_error = create_error
        self.history = history or {"orders": []}
        self.payment_link = payment_link
        self.calls = []

    def create_payment_link(self, address_id):
        self.calls.append(("create_payment_link", address_id))
        if self.create_error:
            raise TimeoutError("ambiguous remote timeout")
        return {
            "orderId": "zepto-order-1",
            "orderCode": "Z123",
            "paymentLink": self.payment_link,
            "toPay": self.total,
        }

    def check_payment_status(self, order_id, *, poll=False):
        self.calls.append(("check_payment_status", order_id, poll))
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"orderId": order_id, "paymentStatus": status}

    def list_order_history(self):
        self.calls.append(("list_order_history",))
        return self.history


class FakeExecutor:
    def __init__(self, *, credential_used=True, error=False, redirects=None):
        self.credential_used = credential_used
        self.error = error
        self.redirects = redirects or []
        self.calls = []

    def execute(self, **checkout_fields):
        self.calls.append(checkout_fields)
        policy = checkout_fields["redirect_policy"]
        policy.validate_url(checkout_fields["payment_link"])
        for redirect in self.redirects:
            policy.validate_url(redirect)
        if self.error:
            raise RuntimeError("browser disconnected")
        return {
            "credential_used": self.credential_used,
            "visited_urls": [checkout_fields["payment_link"], *self.redirects],
        }


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    database = Database(f"sqlite:///{tmp_path / 'checkout.db'}")
    database.create_schema()
    repository = RestockRepository(database)
    reports = []
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("ZEPTO_REAL_PAYMENT_ENABLED", "1")
    monkeypatch.setattr(
        prava_client,
        "report_checkout_outcome",
        lambda session_id, txn_ref_id, status: reports.append(
            (session_id, txn_ref_id, status)
        )
        or {"status": "confirmed"},
    )
    monkeypatch.setattr(
        prava_client,
        "get_payment_result_status",
        lambda _session_id: "awaiting_result",
    )
    prava_client._CREDENTIALS.clear()
    zepto_checkout.configure_real_checkout_runtime(None)
    yield repository, reports
    zepto_checkout.configure_real_checkout_runtime(None)
    prava_client._CREDENTIALS.clear()


def add_credential(reference="credential-1"):
    prava_client._CREDENTIALS[reference] = {
        "token": "fake-network-token",
        "dynamic_cvv": "123",
        "expiry_month": "12",
        "expiry_year": "2099",
        "session_id": "session-1",
        "txn_ref_id": "txn-1",
        "created_at": datetime.now(timezone.utc),
        "consumed_at": None,
    }
    return reference


def install(repository, client, executor):
    zepto_checkout.configure_real_checkout_runtime(
        zepto_checkout.RealCheckoutRuntime(
            repository=repository,
            client=client,
            address_id="address-1",
            executor=executor,
            redirect_policy=zepto_checkout.PaymentRedirectPolicy(("checkout.juspay.in",)),
        )
    )


def checkout(reference="credential-1", key="idem-1", amount="412.50"):
    return zepto_checkout.complete_checkout(reference, "coffee-500g", amount, key)


def test_no_executor_fails_before_mcp_mutation(boundary):
    repository, reports = boundary
    client = FakeZeptoClient()
    install(repository, client, None)
    add_credential()

    with pytest.raises(RuntimeError, match="executor/redirect policy is not configured"):
        checkout()

    assert client.calls == []
    assert repository.get_merchant_checkout_attempt("idem-1") is None
    assert reports == []


def test_success_consumes_once_reports_and_persists_no_secrets(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(statuses=["SUCCESS"])
    executor = FakeExecutor()
    install(repository, client, executor)
    add_credential()

    result = checkout()

    assert result["status"] == "completed"
    assert reports == [("session-1", "txn-1", "APPROVED")]
    assert len(executor.calls) == 1
    assert "credential-1" not in prava_client._CREDENTIALS
    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["state"] == "completed"
    assert attempt["credential_used"] is True
    assert attempt["prava_reported"] is True
    serialized = str(attempt).lower()
    for forbidden in (
        "fake-network-token",
        "dynamic_cvv",
        "paymentlink",
        "payment_link",
        "checkout.juspay.in",
    ):
        assert forbidden not in serialized
    column_names = {column.name.lower() for column in MerchantCheckoutAttemptRow.__table__.columns}
    assert not any(
        fragment in column_name
        for column_name in column_names
        for fragment in ("token", "cvv", "expiry", "payment_link", "paymentlink")
    )


def test_pending_status_is_polled_before_success(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(statuses=["PENDING", "SUCCESS"])
    install(repository, client, FakeExecutor())
    add_credential()

    assert checkout()["status"] == "completed"
    assert ("check_payment_status", "zepto-order-1", False) in client.calls
    assert ("check_payment_status", "zepto-order-1", True) in client.calls
    assert reports == [("session-1", "txn-1", "APPROVED")]


def test_decline_reports_only_after_executor_used_credential(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(statuses=["FAILED"])
    install(repository, client, FakeExecutor(credential_used=True))
    add_credential()

    result = checkout()

    assert result["status"] == "failed"
    assert reports == [("session-1", "txn-1", "DECLINED")]
    assert repository.get_merchant_checkout_attempt("idem-1")["state"] == "declined"


def test_terminal_failure_is_reported_after_credential_exposure(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(statuses=["FAILED"])
    install(repository, client, FakeExecutor(credential_used=False))
    add_credential()

    result = checkout()

    assert result["status"] == "failed"
    assert reports == [("session-1", "txn-1", "DECLINED")]
    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["state"] == "declined"
    assert attempt["credential_used"] is False
    assert attempt["credential_exposed"] is True
    assert attempt["prava_reported"] is True


def test_ambiguous_order_creation_reconciles_history_and_never_recreates(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(create_error=True)
    install(repository, client, FakeExecutor())
    add_credential()

    first = checkout()
    second = checkout()

    assert first["status"] == second["status"] == "pending"
    assert [call[0] for call in client.calls].count("create_payment_link") == 1
    assert [call[0] for call in client.calls].count("list_order_history") == 1
    assert reports == []
    assert repository.get_merchant_checkout_attempt("idem-1")["state"] == "ambiguous"


def test_duplicate_idempotency_returns_existing_terminal_result(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(statuses=["SUCCESS"])
    executor = FakeExecutor()
    install(repository, client, executor)
    add_credential()

    first = checkout()
    second = checkout(reference="already-gone")

    assert first == second
    assert [call[0] for call in client.calls].count("create_payment_link") == 1
    assert len(executor.calls) == 1
    assert reports == [("session-1", "txn-1", "APPROVED")]


def test_price_mismatch_stops_before_credential_or_executor(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(total="500.00")
    executor = FakeExecutor()
    install(repository, client, executor)
    add_credential()

    result = checkout()

    assert result["status"] == "price_changed"
    assert executor.calls == []
    assert reports == []
    assert prava_client._CREDENTIALS["credential-1"]["token"] == "fake-network-token"
    assert repository.get_merchant_checkout_attempt("idem-1")["state"] == "price_changed"


def test_ambiguous_browser_failure_uses_order_history_without_false_report(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(
        statuses=["PENDING", "PENDING"],
        history={"orders": [{"orderId": "zepto-order-1", "status": "PENDING"}]},
    )
    install(repository, client, FakeExecutor(error=True))
    add_credential()

    result = checkout()

    assert result["status"] == "pending"
    assert ("list_order_history",) in client.calls
    assert reports == []
    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["credential_used"] is False
    assert attempt["prava_reported"] is False


def test_unapproved_payment_host_fails_closed_before_credential_exposure(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(payment_link="https://evil.example/steal")
    executor = FakeExecutor()
    install(repository, client, executor)
    add_credential()

    with pytest.raises(zepto_checkout.ZeptoMCPError, match="allowlist"):
        checkout()

    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["state"] == "ambiguous"
    assert attempt["credential_exposed"] is False
    assert executor.calls == []
    assert reports == []


def test_executor_validates_redirect_before_navigation(boundary):
    repository, reports = boundary
    client = FakeZeptoClient(statuses=["PENDING", "PENDING"])
    executor = FakeExecutor(redirects=["https://attacker.example/callback"])
    install(repository, client, executor)
    add_credential()

    result = checkout()

    assert result["status"] == "pending"
    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["credential_exposed"] is True
    assert attempt["state"] == "pending"
    assert reports == []


def test_crash_after_exposure_marker_never_consumes_or_executes_twice(
    boundary, monkeypatch
):
    repository, reports = boundary
    client = FakeZeptoClient(statuses=["SUCCESS"])
    executor = FakeExecutor()
    install(repository, client, executor)
    add_credential()
    original_consume = prava_client.consume_credential
    calls = []

    def crash_once(reference):
        calls.append(reference)
        raise RuntimeError("process died before consume")

    monkeypatch.setattr(prava_client, "consume_credential", crash_once)
    with pytest.raises(RuntimeError, match="process died"):
        checkout()

    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["state"] == "executing"
    assert attempt["credential_exposed"] is True
    assert executor.calls == []

    monkeypatch.setattr(prava_client, "consume_credential", original_consume)
    result = zepto_checkout.reconcile_checkout("idem-1")
    assert result["status"] == "completed"
    assert calls == ["credential-1"]
    assert executor.calls == []
    assert reports == [("session-1", "txn-1", "APPROVED")]


def test_ambiguous_report_is_reconciled_without_duplicate_post(boundary, monkeypatch):
    repository, _reports = boundary
    client = FakeZeptoClient(statuses=["SUCCESS"])
    install(repository, client, FakeExecutor())
    add_credential()
    posts = []

    def ambiguous_post(session_id, txn_ref_id, status):
        posts.append((session_id, txn_ref_id, status))
        raise TimeoutError("response lost after remote commit")

    monkeypatch.setattr(prava_client, "report_checkout_outcome", ambiguous_post)
    assert checkout()["status"] == "completed"
    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["report_state"] == "ambiguous"
    assert attempt["report_attempts"] == 1

    monkeypatch.setattr(
        prava_client, "get_payment_result_status", lambda _session_id: "awaiting_result"
    )
    assert zepto_checkout.reconcile_checkout("idem-1")["status"] == "completed"
    assert posts == [("session-1", "txn-1", "APPROVED")]
    assert repository.get_merchant_checkout_attempt("idem-1")["report_state"] == "ambiguous"

    monkeypatch.setattr(
        prava_client, "get_payment_result_status", lambda _session_id: "completed"
    )
    assert zepto_checkout.reconcile_checkout("idem-1")["status"] == "completed"
    assert posts == [("session-1", "txn-1", "APPROVED")]
    attempt = repository.get_merchant_checkout_attempt("idem-1")
    assert attempt["report_state"] == "confirmed"
    assert attempt["prava_reported"] is True


def test_checkout_attempt_state_transition_is_compare_and_swap(boundary):
    repository, _reports = boundary
    attempt, created = repository.reserve_merchant_checkout_attempt(
        idempotency_key="cas-1",
        merchant="zepto",
        merchant_sku_id="coffee-500g",
        expected_amount=Decimal("412.50"),
        currency="INR",
        prava_session_id="session-1",
        prava_txn_ref_id="txn-1",
    )
    assert created and attempt["state"] == "reserved"
    repository.update_merchant_checkout_attempt(
        "cas-1", expected_states={"reserved"}, state="creating_order"
    )
    with pytest.raises(ValueError, match="compare-and-swap"):
        repository.update_merchant_checkout_attempt(
            "cas-1", expected_states={"reserved"}, state="creating_order"
        )
