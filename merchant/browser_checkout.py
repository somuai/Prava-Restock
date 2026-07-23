"""Browser-automation boundary for the payment-form step of merchant checkout.

Prava confirmed: order/cart creation IS available via existing merchant MCP
skills, but the actual checkout/payment-form step — entering the one-time card
number, CVV, and expiry into the merchant's real payment form — has NO MCP
support and must be built as browser automation.

This module implements ``complete_payment_via_browser`` using Playwright.
Because it depends on unversioned merchant checkout DOM (fragile by nature),
it explicitly distinguishes automation failures (selector not found, page-
structure change) from expected payment failures (test-card decline).

If browser automation proves too fragile within the hackathon's time budget,
the accepted fallback is a clearly disclosed simulated/recorded version of
this step — same disclosure standard as every other mock in this project.
Do not silently degrade to a fake without labeling it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AutomationFailure(Exception):
    """Raised when browser automation fails for a structural reason.

    This is NOT a payment failure — the payment was never attempted.
    Examples: selector not found, page structure changed, navigation timeout.
    These need different handling and different messaging in the demo than a
    legitimate payment decline.
    """


class PaymentDecline(Exception):
    """Raised when the payment was correctly submitted but declined.

    This is the EXPECTED outcome with Prava sandbox test cards — the card
    is valid in Prava's ecosystem but will be declined by the real merchant
    because it's a test card. This is success for demo purposes.
    """


@dataclass(frozen=True)
class PaymentCredential:
    """One-time card credential from Prava, consumed exactly once."""

    card_number: str
    cvv: str
    expiry_month: str
    expiry_year: str


@dataclass(frozen=True)
class PaymentResult:
    """Outcome of a browser-automated payment attempt."""

    success: bool
    declined_by_merchant: bool
    error_code: str | None
    automation_failure: bool
    visited_urls: list[str]


async def complete_payment_via_browser(
    checkout_url: str,
    credential: PaymentCredential,
    *,
    card_number_selector: str = 'input[name="card_number"], input[name="cardNumber"], input[id="card-number"]',
    cvv_selector: str = 'input[name="cvv"], input[name="card_cvv"], input[id="cvv"]',
    expiry_selector: str = 'input[name="card_expiry"], input[name="expiry"], input[id="card-expiry"]',
    expiry_month_selector: str | None = None,
    expiry_year_selector: str | None = None,
    pay_button_selector: str = 'button[type="submit"], button:has-text("Pay"), button:has-text("pay")',
    timeout_ms: int = 30_000,
) -> PaymentResult:
    """Navigate to a merchant checkout page and fill the payment form.

    Uses Playwright to:
    1. Open the checkout URL
    2. Fill card number, CVV, and expiry from the Prava credential
    3. Click the Pay button
    4. Wait for the result

    Raises AutomationFailure if a selector is not found or the page structure
    does not match expectations. This is distinct from PaymentDecline, which
    is the expected outcome with test cards.
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        raise AutomationFailure(
            "playwright is not installed; install with: pip install playwright && playwright install chromium"
        )

    visited_urls: list[str] = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Track all navigated URLs for audit
            page.on("framenavigated", lambda frame: (
                visited_urls.append(frame.url) if frame == page.main_frame else None
            ))

            await page.goto(checkout_url, timeout=timeout_ms)
            visited_urls.append(page.url)

            # Fill card number
            try:
                card_input = page.locator(card_number_selector).first
                await card_input.wait_for(state="visible", timeout=timeout_ms // 3)
                await card_input.fill(credential.card_number)
            except (PlaywrightTimeout, Exception) as exc:
                await browser.close()
                raise AutomationFailure(
                    f"card number field not found or not fillable: {exc}"
                ) from exc

            # Fill CVV
            try:
                cvv_input = page.locator(cvv_selector).first
                await cvv_input.wait_for(state="visible", timeout=timeout_ms // 3)
                await cvv_input.fill(credential.cvv)
            except (PlaywrightTimeout, Exception) as exc:
                await browser.close()
                raise AutomationFailure(
                    f"CVV field not found or not fillable: {exc}"
                ) from exc

            # Fill expiry — support both combined and separate month/year fields
            try:
                if expiry_month_selector and expiry_year_selector:
                    month_input = page.locator(expiry_month_selector).first
                    year_input = page.locator(expiry_year_selector).first
                    await month_input.fill(credential.expiry_month)
                    await year_input.fill(credential.expiry_year)
                else:
                    expiry_input = page.locator(expiry_selector).first
                    await expiry_input.wait_for(state="visible", timeout=timeout_ms // 3)
                    await expiry_input.fill(
                        f"{credential.expiry_month}/{credential.expiry_year}"
                    )
            except (PlaywrightTimeout, Exception) as exc:
                await browser.close()
                raise AutomationFailure(
                    f"expiry field not found or not fillable: {exc}"
                ) from exc

            # Click Pay
            try:
                pay_button = page.locator(pay_button_selector).first
                await pay_button.wait_for(state="visible", timeout=timeout_ms // 3)
                await pay_button.click()
            except (PlaywrightTimeout, Exception) as exc:
                await browser.close()
                raise AutomationFailure(
                    f"pay button not found or not clickable: {exc}"
                ) from exc

            # Wait for navigation after clicking Pay
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except PlaywrightTimeout:
                pass  # Some pages don't trigger a full navigation

            visited_urls.append(page.url)

            # Check for decline indicators in the page
            page_text = await page.inner_text("body")
            decline_indicators = [
                "declined", "failed", "unsuccessful", "not approved",
                "card declined", "transaction failed", "payment failed",
            ]
            is_declined = any(
                indicator in page_text.lower() for indicator in decline_indicators
            )

            await browser.close()

            if is_declined:
                return PaymentResult(
                    success=False,
                    declined_by_merchant=True,
                    error_code="PAYMENT_DECLINED_TEST_CARD",
                    automation_failure=False,
                    visited_urls=visited_urls,
                )

            # If we get here without a decline, the payment may have succeeded
            # (unexpected with test cards) or the result page is ambiguous
            return PaymentResult(
                success=True,
                declined_by_merchant=False,
                error_code=None,
                automation_failure=False,
                visited_urls=visited_urls,
            )

    except AutomationFailure:
        raise
    except Exception as exc:
        raise AutomationFailure(
            f"unexpected browser automation error: {exc}"
        ) from exc
