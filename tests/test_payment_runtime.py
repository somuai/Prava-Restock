import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from demo.seed_reset import demo_user, load_seed_items
from merchant import zepto_checkout
from merchant.models import ExecutionMode, MerchantQuote, StockStatus
from merchant.payment_executor import SubprocessBrowserPaymentExecutor
from merchant.quote_provider import build_home_quote_provider
from storage import Database, RestockRepository


def test_real_catalog_and_disclosed_payment_are_independent(tmp_path, monkeypatch) -> None:
    repository = RestockRepository(Database(f"sqlite:///{tmp_path / 'runtime.db'}"))
    repository.create_schema()
    user = demo_user()
    item = next(candidate for candidate in load_seed_items() if candidate.preferred_merchant.value == "zepto")
    repository.upsert_user(user)
    repository.upsert_item(item)
    monkeypatch.setenv("HOME_MERCHANT_MODE", "real")
    monkeypatch.setenv("HOME_PAYMENT_MODE", "disclosed_mock")
    monkeypatch.setenv("ZEPTO_DEVICE_ID", "runtime-only-device")
    monkeypatch.setattr(
        zepto_checkout,
        "prepare_exact_cart_quote",
        lambda *args, **kwargs: MerchantQuote(
            merchant="zepto",
            merchant_sku_id=item.merchant_sku_id,
            product_name=item.name,
            amount=Decimal("381.00"),
            currency="INR",
            stock_status=StockStatus.IN_STOCK,
            quote_reference="real-quote-reference",
            observed_at=datetime.now(timezone.utc),
            execution_mode=ExecutionMode.REAL,
        ),
    )

    quote = build_home_quote_provider(repository).quote_locked(item)
    checkout = zepto_checkout.complete_checkout(
        "unconsumed-reference", item.merchant_sku_id, quote.amount, "real-quote-mock-pay"
    )

    assert quote.execution_mode is ExecutionMode.REAL
    assert checkout["execution_mode"] == "disclosed_mock"
    assert zepto_checkout.merchant_mode() is ExecutionMode.REAL
    assert zepto_checkout.payment_mode() is ExecutionMode.DISCLOSED_MOCK


def test_payment_executor_uses_stdin_and_redacts_child_failure(tmp_path) -> None:
    executable = tmp_path / "payment-runner"
    executable.write_text("#!/bin/sh\ncat >/dev/null\necho token-leak >&2\nexit 9\n")
    executable.chmod(0o700)
    executor = SubprocessBrowserPaymentExecutor(str(executable))

    with pytest.raises(RuntimeError) as failure:
        executor.execute(
            payment_link="https://checkout.example.test/pay",
            token="sensitive-token",
            dynamic_cvv="123",
            expiry_month="12",
            expiry_year="2030",
            redirect_policy=zepto_checkout.PaymentRedirectPolicy(("checkout.example.test",)),
        )

    message = str(failure.value)
    assert "sensitive-token" not in message
    assert "token-leak" not in message


def test_payment_executor_returns_only_sanitized_result(tmp_path) -> None:
    executable = tmp_path / "payment-runner"
    executable.write_text(
        "#!/bin/sh\n"
        "python3 -c 'import json,sys; data=json.load(sys.stdin); "
        "print(json.dumps({\"visited_urls\":[data[\"payment_link\"]],"
        "\"credential_used\":True,\"echo\":data[\"token\"]}))'\n"
    )
    executable.chmod(0o700)
    executor = SubprocessBrowserPaymentExecutor(str(executable))

    result = executor.execute(
        payment_link="https://checkout.example.test/pay",
        token="sensitive-token",
        dynamic_cvv="123",
        expiry_month="12",
        expiry_year="2030",
        redirect_policy=zepto_checkout.PaymentRedirectPolicy(("checkout.example.test",)),
    )

    assert result == {
        "visited_urls": ["https://checkout.example.test/pay"],
        "credential_used": True,
    }
    assert "sensitive-token" not in json.dumps(result)
