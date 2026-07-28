"""Tests for the browser-automation payment boundary.

These tests use a local fixture HTML page mimicking a generic checkout form,
not the real Zepto site. They validate that:
- Successful form fill works against a standard form shape
- Missing selectors raise AutomationFailure (not PaymentDecline)
- Decline indicators are correctly detected

NOTE: These tests require playwright to be installed. They are skipped if
playwright is not available.
"""

import asyncio
from pathlib import Path
from textwrap import dedent

import pytest

try:
    import playwright  # noqa: F401
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from merchant.browser_checkout import (
    AutomationFailure,
    MerchantUnavailable,
    PaymentCredential,
    complete_payment_via_browser,
)


skip_no_playwright = pytest.mark.skipif(
    not HAS_PLAYWRIGHT,
    reason="playwright is not installed",
)

TEST_CREDENTIAL = PaymentCredential(
    card_number="4111111111111111",
    cvv="123",
    expiry_month="12",
    expiry_year="2028",
)


STANDARD_CHECKOUT_HTML = dedent("""\
<!DOCTYPE html>
<html>
<head><title>Test Checkout</title></head>
<body>
  <h1>Payment</h1>
  <form id="payment-form">
    <input name="card_number" type="text" placeholder="Card Number" />
    <input name="card_expiry" type="text" placeholder="MM/YY" />
    <input name="cvv" type="text" placeholder="CVV" />
    <button type="submit">Pay Now</button>
  </form>
  <script>
    document.getElementById('payment-form').addEventListener('submit', function(e) {
      e.preventDefault();
      document.body.innerHTML = '<h1>Payment Declined</h1><p>Your card was declined.</p>';
    });
  </script>
</body>
</html>
""")

MISSING_FIELDS_HTML = dedent("""\
<!DOCTYPE html>
<html>
<head><title>Broken Checkout</title></head>
<body>
  <h1>Payment</h1>
  <p>This form is missing the card fields.</p>
  <button type="submit">Pay</button>
</body>
</html>
""")

SUCCESS_CHECKOUT_HTML = dedent("""\
<!DOCTYPE html>
<html>
<head><title>Test Checkout</title></head>
<body>
  <h1>Payment</h1>
  <form id="payment-form">
    <input name="card_number" type="text" />
    <input name="card_expiry" type="text" />
    <input name="cvv" type="text" />
    <button type="submit">Pay</button>
  </form>
  <script>
    document.getElementById('payment-form').addEventListener('submit', function(e) {
      e.preventDefault();
      document.body.innerHTML = '<h1>Payment Successful</h1><p>Thank you for your purchase.</p>';
    });
  </script>
</body>
</html>
""")


@pytest.fixture
def checkout_page(tmp_path: Path):
    """Write an HTML fixture and return its file:// URL."""
    def _write(html_content: str) -> str:
        page_path = tmp_path / "checkout.html"
        page_path.write_text(html_content, encoding="utf-8")
        return f"file://{page_path}"
    return _write


@pytest.fixture(autouse=True)
def merchant_is_reachable(monkeypatch) -> None:
    """Browser-shape tests exercise checkout, not the separate health probe."""
    monkeypatch.setattr(
        "merchant.browser_checkout.check_merchant_availability",
        lambda _url: True,
    )


@skip_no_playwright
def test_form_fill_detects_decline(checkout_page) -> None:
    """A standard checkout form with a decline result is correctly identified."""
    url = checkout_page(STANDARD_CHECKOUT_HTML)
    result = asyncio.run(
        complete_payment_via_browser(
            url, TEST_CREDENTIAL, timeout_ms=10_000
        )
    )
    assert result.declined_by_merchant is True
    assert result.automation_failure is False
    assert result.error_code == "PAYMENT_DECLINED_TEST_CARD"
    assert len(result.visited_urls) >= 1


@skip_no_playwright
def test_absence_of_decline_text_is_ambiguous_without_success_evidence(
    checkout_page,
) -> None:
    """A quiet page is pending reconciliation, not optimistically successful."""
    url = checkout_page(SUCCESS_CHECKOUT_HTML)
    result = asyncio.run(
        complete_payment_via_browser(url, TEST_CREDENTIAL, timeout_ms=10_000)
    )

    assert result.success is False
    assert result.declined_by_merchant is False
    assert result.error_code == "PAYMENT_RESULT_AMBIGUOUS"
    assert result.disclosure_reason == "payment_result_ambiguous"


def test_merchant_down_uses_disclosed_mock_only_when_explicitly_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "merchant.browser_checkout.check_merchant_availability",
        lambda _url: False,
    )

    result = asyncio.run(
        complete_payment_via_browser(
            "https://merchant.invalid/checkout",
            TEST_CREDENTIAL,
            allow_disclosed_mock_on_merchant_unavailable=True,
        )
    )

    assert result.success is True
    assert result.execution_mode == "disclosed_mock"
    assert result.disclosure_reason == "merchant_unavailable"


def test_merchant_down_fails_when_disclosed_mock_is_not_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "merchant.browser_checkout.check_merchant_availability",
        lambda _url: False,
    )

    with pytest.raises(MerchantUnavailable, match="merchant is unavailable"):
        asyncio.run(
            complete_payment_via_browser(
                "https://merchant.invalid/checkout",
                TEST_CREDENTIAL,
            )
        )


@skip_no_playwright
def test_missing_fields_raises_automation_failure(checkout_page) -> None:
    """Missing card input fields raise AutomationFailure, not PaymentDecline."""
    url = checkout_page(MISSING_FIELDS_HTML)
    with pytest.raises(AutomationFailure, match="card number field not found"):
        asyncio.run(
            complete_payment_via_browser(
                url, TEST_CREDENTIAL, timeout_ms=5_000
            )
        )


@skip_no_playwright
def test_successful_payment_detected(checkout_page) -> None:
    """A form that reports success is correctly identified."""
    url = checkout_page(SUCCESS_CHECKOUT_HTML)
    result = asyncio.run(
        complete_payment_via_browser(
            url,
            TEST_CREDENTIAL,
            success_selector="h1:has-text('Payment Successful')",
            timeout_ms=10_000,
        )
    )
    assert result.success is True
    assert result.declined_by_merchant is False
    assert result.automation_failure is False


def test_automation_failure_without_playwright() -> None:
    """If playwright is missing, AutomationFailure is raised immediately."""
    if HAS_PLAYWRIGHT:
        pytest.skip("playwright is installed")
    with pytest.raises(AutomationFailure, match="playwright is not installed"):
        asyncio.run(
            complete_payment_via_browser(
                "https://example.com", TEST_CREDENTIAL
            )
        )
